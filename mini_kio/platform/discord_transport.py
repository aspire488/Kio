"""
discord_transport.py — KIO Discord Transport

Reuses existing KIO runtime via route().
No duplicated orchestration, memory, or Media Intelligence.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Discord message handler — reuses KIO's route()
# ---------------------------------------------------------------------------

async def _handle_discord_message(message, client) -> None:
    """Process a single Discord message through the KIO runtime."""
    from mini_kio.core.command_router import route

    user_id = message.author.id
    content = message.content.strip()
    channel_id = message.channel.id
    author_name = str(message.author)

    logger.info(
        "[DISCORD_MESSAGE] author=%s channel=%s user_id=%s content=%s",
        author_name, channel_id, user_id, content,
    )

    if not content:
        return

    # Slash-like commands parsed from text
    if content.startswith("/kio "):
        content = content[5:].strip()
    elif content == "/status":
        await _send_status(message, client)
        return
    elif content.startswith("/"):
        return

    try:
        t0 = time.time()
        reply = await asyncio.to_thread(route, content, user_id=user_id, channel="discord")
        elapsed = time.time() - t0
        logger.info(
            "[DISCORD_RESPONSE] author=%s elapsed=%.2fs response_len=%d",
            author_name, elapsed, len(reply),
        )
    except BaseException as exc:
        logger.exception("[DISCORD_ERROR] author=%s error=%s", author_name, exc)
        reply = "KIO encountered an internal error but is still running."

    if reply and len(reply) <= 2000:
        await message.channel.send(reply)
    elif reply:
        for i in range(0, len(reply), 1900):
            await message.channel.send(reply[i:i+1900])


async def _send_status(message, client) -> None:
    """Reply with KIO runtime health summary."""
    from mini_kio.core.runtime import get_runtime_snapshot

    snap = get_runtime_snapshot()
    status_lines = [
        "```",
        "KIO Status",
        f"  Runtime: {snap.get('state', 'unknown')}",
        f"  Channels: {', '.join(snap.get('channels', ['none']))}",
        f"  Uptime: {snap.get('uptime_ms', 0) // 1000}s",
        f"  Health: {snap.get('health_score', 'N/A')}",
        f"  Integrity: {snap.get('integrity_status', 'healthy')}",
        f"  Warnings: {snap.get('integrity_warning_count', 0)}",
        f"  RAM: {snap.get('ram_mb', 0):.1f} MB",
        "```",
    ]
    reply = "\n".join(status_lines)
    await message.channel.send(reply)
    logger.info("[DISCORD_STATUS] sent for channel=%s", message.channel.id)


# ---------------------------------------------------------------------------
# Async Discord bot runner
# ---------------------------------------------------------------------------

async def _run_discord_bot(token: str) -> None:
    """Run the Discord client with minimal intents."""
    import discord

    intents = discord.Intents.default()
    intents.message_content = True

    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        logger.info("[DISCORD_CONNECTED] user=%s id=%s", client.user, client.user.id)
        print(f"[DISCORD_CONNECTED] Logged in as {client.user} (ID: {client.user.id})")

    @client.event
    async def on_message(message):
        if message.author.bot:
            return
        await _handle_discord_message(message, client)

    @client.event
    async def on_disconnect():
        logger.info("[DISCORD_DISCONNECT]")

    @client.event
    async def on_resumed():
        logger.info("[DISCORD_RECONNECT]")

    async with client:
        await client.start(token)


# ---------------------------------------------------------------------------
# Thread entry point (matches Telegram's run_bot pattern)
# ---------------------------------------------------------------------------

def run_discord(runtime=None) -> None:
    """Synchronous entry point for Discord transport.

    Runs the Discord client in its own asyncio event loop.
    Designed to be called from a thread or directly.
    """
    from mini_kio.core.config import DISCORD_BOT_TOKEN

    token = DISCORD_BOT_TOKEN
    if not token:
        logger.error("[DISCORD_ERROR] DISCORD_BOT_TOKEN not set")
        print("ERROR: DISCORD_BOT_TOKEN not configured in .env")
        return

    print("=" * 50)
    print("KIO DISCORD BOT")
    print("=" * 50)

    try:
        asyncio.run(_run_discord_bot(token))
    except KeyboardInterrupt:
        logger.info("[DISCORD_DISCONNECT] reason=KeyboardInterrupt")
        print("\nDiscord bot stopped.")
    except BaseException as exc:
        logger.exception("[DISCORD_ERROR] %s", exc)
        print(f"ERROR: Discord bot failed: {exc}")


# ---------------------------------------------------------------------------
# Threaded launcher (for coexistence with Telegram)
# ---------------------------------------------------------------------------

_DISCORD_THREAD: Optional[threading.Thread] = None


def start_discord_thread() -> bool:
    """Start Discord transport in a daemon thread.

    Returns True if thread was started, False if Discord is not configured.
    """
    global _DISCORD_THREAD

    from mini_kio.core.config import DISCORD_BOT_TOKEN

    if not DISCORD_BOT_TOKEN:
        return False

    if _DISCORD_THREAD is not None and _DISCORD_THREAD.is_alive():
        logger.info("[DISCORD] thread already running")
        return True

    _DISCORD_THREAD = threading.Thread(
        target=run_discord,
        args=(),
        daemon=True,
        name="discord-transport",
    )
    _DISCORD_THREAD.start()
    logger.info("[DISCORD] thread started")
    return True


def stop_discord_thread() -> None:
    """Signal Discord thread to stop (daemon thread will exit on main exit)."""
    global _DISCORD_THREAD
    # Daemon thread exits when main process exits — no explicit stop needed.
    _DISCORD_THREAD = None
    logger.info("[DISCORD] thread released")
