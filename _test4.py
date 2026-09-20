#!/usr/bin/env python3
"""TEST 4: Send Telegram voice note -> STT -> pipeline -> TTS -> voice reply."""
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
VOICE_FILE = str(Path(__file__).resolve().parent / "_voice_test4_v2.ogg")

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start(phone=PHONE)
    bot = await client.get_entity("KIO_Runtime_bot")
    
    print(f"Uploading voice note from {VOICE_FILE} ({os.path.getsize(VOICE_FILE)} bytes)...", flush=True)
    t0 = time.monotonic()
    sent = await client.send_file(bot, VOICE_FILE, voice_note=True, voice_duration=3)
    print(f"Sent voice msg_id={sent.id}", flush=True)

    for _ in range(60):
        await asyncio.sleep(3)
        async for m in client.iter_messages(bot, limit=5, reverse=False):
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
                text = m.text or ""
                print(f"TEST4 REPLY ({elapsed:.1f}s): text={text[:200]!r} media={media_type} size={size}", flush=True)
                if has_voice and media_type == "voice" and size > 1000:
                    print(f"TEST4 PASS (voice {size} bytes, STT+TTS chain complete)", flush=True)
                elif text and not has_voice:
                    if "4" in text or "two plus two" in text.lower() or "2+2" in text:
                        print(f"TEST4 PARTIAL (correct text answer but no voice: {text[:100]!r})", flush=True)
                    else:
                        print(f"TEST4 FAIL (text only, no voice: {text[:100]!r})", flush=True)
                elif not m.text and not has_voice:
                    print("TEST4 FAIL (empty reply)", flush=True)
                else:
                    print("TEST4 UNCLEAR", flush=True)
                await client.disconnect()
                return

    print("TEST4 TIMEOUT", flush=True)
    await client.disconnect()

asyncio.run(main())
