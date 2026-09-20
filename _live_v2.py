#!/usr/bin/env python3
"""Strict live validation: ONE message, measure full roundtrip, 10s threshold."""
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
TIMEOUT = 15
THRESHOLD = 10.0


async def run_test(test_num, test_category, text, timeout=TIMEOUT):
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start(phone=PHONE)
    print(f"TEST {test_num} — {test_category}")
    print(f"  Sending: {text!r}")

    bot = await client.get_entity(BOT_USERNAME)
    t0 = time.monotonic()
    msg = await client.send_message(bot, text)
    msg_id = msg.id
    send_time = time.monotonic() - t0
    print(f"  Send latency: {send_time:.2f}s")

    deadline = t0 + timeout
    result = None
    while time.monotonic() < deadline:
        await asyncio.sleep(1)
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
                text_preview = (m.text or "")[:600]
                file_size = m.file.size if m.file and hasattr(m.file, 'size') else 0
                result = {
                    "text": text_preview,
                    "media_type": media_type,
                    "voice": has_voice,
                    "size": file_size,
                    "elapsed": elapsed,
                }
                break
        if result:
            break

    await client.disconnect()

    if not result:
        print(f"  RESULT: FAIL (no response within {timeout}s)")
        return False

    passed = result["elapsed"] <= THRESHOLD
    status = "PASS" if passed else "FAIL"
    print(f"  Response ({result['elapsed']:.2f}s):")
    print(f"    Text: {result['text']!r}")
    print(f"    Media: {result['media_type'] or 'none'}")
    print(f"    Voice: {result['voice']}")
    print(f"  RESULT: {status} ({result['elapsed']:.2f}s, threshold={THRESHOLD}s)")
    return passed


if __name__ == "__main__":
    num = sys.argv[1] if len(sys.argv) > 1 else "1"
    cat = sys.argv[2] if len(sys.argv) > 2 else "manual"
    msg = sys.argv[3] if len(sys.argv) > 3 else "Hello KIO"
    asyncio.run(run_test(num, cat, msg))
