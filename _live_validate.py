#!/usr/bin/env python3
"""Bounded live validation: ONE message, WAIT, OBSERVE, report."""
from __future__ import annotations
import asyncio, os, sys, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

sys.stdout.reconfigure(encoding="utf-8")

from telethon import TelegramClient
from telethon.tl.types import MessageMediaDocument, DocumentAttributeAudio, MessageMediaPhoto

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
PHONE = os.getenv("TELEGRAM_USER_PHONE", "")
SESSION = str(Path(__file__).resolve().parent / ".telegram_sessions" / "kio_test_user.session")
BOT_USERNAME = "KIO_Runtime_bot"
TIMEOUT = 90


async def send_and_observe(client, text, test_label, timeout=TIMEOUT):
    """Send one message, wait for reply, print observation."""
    bot = await client.get_entity(BOT_USERNAME)
    t0 = time.monotonic()
    msg = await client.send_message(bot, text)
    msg_id = msg.id
    print(f"\n{'='*60}")
    print(f"SENT: {text!r}")
    print(f"Waiting for reply (timeout {timeout}s)...")

    deadline = t0 + timeout
    while time.monotonic() < deadline:
        async for m in client.iter_messages(bot, limit=5, reverse=False):
            if m.date and m.id > msg_id:
                elapsed = time.monotonic() - t0
                has_voice = False
                media_type = None
                if m.media:
                    if isinstance(m.media, MessageMediaDocument):
                        doc = m.media.document
                        if doc:
                            for attr in doc.attributes:
                                if isinstance(attr, DocumentAttributeAudio):
                                    has_voice = True
                                    media_type = "voice"
                                    break
                        if not has_voice:
                            media_type = "document"
                    elif isinstance(m.media, MessageMediaPhoto):
                        media_type = "photo"
                text_preview = (m.text or "")[:500]
                file_size = m.file.size if m.file and hasattr(m.file, 'size') else 0

                print(f"\n--- RESPONSE ({elapsed:.1f}s) ---")
                print(f"  Text: {text_preview!r}")
                print(f"  Media: {media_type or 'none'}")
                print(f"  Voice: {has_voice}")
                print(f"  Size: {file_size}")
                return {
                    "text": text_preview,
                    "media_type": media_type,
                    "voice": has_voice,
                    "size": file_size,
                    "elapsed": elapsed,
                }
        await asyncio.sleep(1)

    print(f"\n  TIMEOUT after {timeout}s — no reply received")
    return None


async def main():
    test_message = sys.argv[1] if len(sys.argv) > 1 else "Hello KIO"
    test_label = sys.argv[2] if len(sys.argv) > 2 else "manual"

    print(f"Live validation — Test: {test_label}")
    print(f"Bot: {BOT_USERNAME}")
    print(f"Session: {SESSION}")

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start(phone=PHONE)
    print("Connected to Telegram.")

    result = await send_and_observe(client, test_message, test_label)

    if result:
        print(f"\n=== RESULT: PASS (replied in {result['elapsed']:.1f}s) ===")
    else:
        print(f"\n=== RESULT: FAIL (no response) ===")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
