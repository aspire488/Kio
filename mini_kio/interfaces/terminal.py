from __future__ import annotations

import logging
import sys
import time

from mini_kio.core.config import TERMINAL_ENABLED

logger = logging.getLogger(__name__)


def _shutdown_requested(runtime=None) -> bool:
    if runtime is None:
        return False
    try:
        return bool(runtime.shutdown_requested)
    except Exception:
        return False


def run_terminal(runtime=None) -> None:
    if not TERMINAL_ENABLED:
        return

    try:
        import readline  # command history (↑/↓)
    except ImportError:
        pass

    from mini_kio.core.command_router import route

    print("=" * 50)
    print("KIO Terminal")
    print("=" * 50)
    print('Type "exit" or press Ctrl+D to quit.')

    while not _shutdown_requested(runtime):
        try:
            text = input("\nYou > ")
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            continue

        if text.lower() in ("exit", "quit"):
            break
        if not text.strip():
            continue

        # Show response indicator (like Telegram's typing indicator)
        print("KIO > ", end="", flush=True)
        time.sleep(0.2)

        try:
            reply = route(text, user_id=0, channel="terminal")
            print(reply)
        except BaseException as exc:
            logger.exception("[TERMINAL] error: %s", exc)
            print("KIO encountered an error but is still running.")

    # Signal clean shutdown so host_runtime() can exit — ONLY when the
    # terminal is the sole channel. When other channels (Telegram/Discord)
    # share this runtime, the terminal exiting (e.g. stdin EOF on a
    # non-interactive launch) must not shut down the whole runtime.
    if runtime is not None:
        try:
            from mini_kio.core.config import DISCORD_BOT_TOKEN, TELEGRAM_TOKEN
            if not TELEGRAM_TOKEN and not DISCORD_BOT_TOKEN:
                runtime.request_shutdown()
        except Exception:
            pass

    logger.info("[TERMINAL] session ended")
