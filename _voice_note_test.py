#!/usr/bin/env python3
"""Send voice note to KIO bot and check response."""
from __future__ import annotations
import asyncio, os, sys, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

from telethon import TelegramClient
from telethon.tl.types import MessageMediaDocument, DocumentAttributeAudio

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
PHONE = os.getenv("TELEGRAM_USER_PHONE", "")
SESSION = str(Path(__file__).resolve().parent / ".telegram_sessions" / "kio_test_user.session")
BOT = "KIO_Runtime_bot"
TIMEOUT = 120
VOICE_FILE = str(Path(__file__).resolve().parent / "_test_voice_input.ogg")

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"Logged in as {me.first_name} (id={me.id})")

    bot = await client.get_entity(BOT)
    
    # Send voice note
    t0 = time.monotonic()
    print(f"Sending voice note: {VOICE_FILE}")
    sent = await client.send_file(bot, VOICE_FILE, voice_note=True, caption="Hey KIO, what is two plus two?")
    msg_id = sent.id
    print(f"Voice sent (msg_id={msg_id})")
    
    # Wait for reply
    deadline = t0 + TIMEOUT
    last_print = t0
    while time.monotonic() < deadline:
        async for m in client.iter_messages(bot, limit=5):
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
                                    media_type = "voice/audio"
                                    break
                        if not has_voice:
                            media_type = "document"
                    else:
                        media_type = str(type(m.media).__name__)
                text_preview = (m.text or "")[:300]
                print(f"\nREPLY ({elapsed:.1f}s):")
                print(f"  text: {text_preview!r}")
                print(f"  media: {media_type} voice: {has_voice}")
                if m.file and hasattr(m.file, 'size'):
                    print(f"  file_size: {m.file.size} bytes")
                
                if text_preview or has_voice:
                    if has_voice:
                        print("\nTEST E (voice-note STT + voice reply): PASS")
                    elif text_preview:
                        print(f"\nTEST E (voice-note STT): reply={text_preview!r}")
                        print("TEST E: PARTIAL (STT worked, got text reply)")
                    break
                return
        now = time.monotonic()
        if now - last_print > 10:
            print(f"  waiting... ({now - t0:.0f}s)")
            last_print = now
        await asyncio.sleep(1)
    else:
        print(f"TIMEOUT after {TIMEOUT}s")
    
    await client.disconnect()

asyncio.run(main())
