#!/usr/bin/env python3
"""TEST 1: Hello KIO -> text response."""
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
    print("Connected", flush=True)
    
    bot = await client.get_entity("KIO_Runtime_bot")
    t0 = time.monotonic()
    sent = await client.send_message(bot, "Hello KIO")
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
                    elif isinstance(m.media, MessageMediaPhoto):
                        media_type = "photo"
                size = m.file.size if m.file and hasattr(m.file, 'size') else 0
                print(f"TEST1 REPLY ({elapsed:.1f}s): text={m.text!r} media={media_type} size={size}", flush=True)
                if media_type == "voice":
                    print("TEST1 PASS (voice response)", flush=True)
                elif media_type == "document":
                    print("TEST1 FAIL (got document instead of text)", flush=True)
                elif m.text:
                    print("TEST1 PASS (text response)", flush=True)
                else:
                    print("TEST1 UNCLEAR", flush=True)
                await client.disconnect()
                return
    
    print("TEST1 TIMEOUT", flush=True)
    await client.disconnect()

asyncio.run(main())
