#!/usr/bin/env python3
"""TEST 2: Say that out loud -> voice reply, not text."""
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

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start(phone=PHONE)
    bot = await client.get_entity("KIO_Runtime_bot")
    t0 = time.monotonic()
    sent = await client.send_message(bot, "Say that out loud")
    print(f"Sent msg_id={sent.id}", flush=True)

    for _ in range(45):
        await asyncio.sleep(2)
        async for m in client.iter_messages(bot, limit=3, reverse=False):
            if m.date and m.id > sent.id:
                elapsed = time.monotonic() - t0
                has_voice = False
                media_type = None
                if m.media:
                    if isinstance(m.media, MessageMediaDocument):
                        for attr in (m.media.document.attributes or []):
                            if isinstance(attr, DocumentAttributeAudio):
                                has_voice = True
                                media_type = "voice"
                                break
                        if not has_voice:
                            media_type = "document"
                size = m.file.size if m.file and hasattr(m.file, 'size') else 0
                text = m.text or ""
                print(f"TEST2 REPLY ({elapsed:.1f}s): text={text[:200]!r} media={media_type} size={size}", flush=True)
                if has_voice and media_type == "voice" and size > 1000:
                    print(f"TEST2 PASS (voice {size} bytes)", flush=True)
                elif text and not has_voice:
                    print(f"TEST2 FAIL (got text instead of voice: {text[:100]!r})", flush=True)
                else:
                    print("TEST2 UNCLEAR", flush=True)
                await client.disconnect()
                return

    print("TEST2 TIMEOUT", flush=True)
    await client.disconnect()

asyncio.run(main())
