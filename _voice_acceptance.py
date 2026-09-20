#!/usr/bin/env python3
"""Minimal voice acceptance test via Telethon — acts as user, sends to running KIO bot."""
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
TIMEOUT = 90  # seconds to wait for bot reply

async def send_and_wait(client, text, label, wait_media=False):
    """Send text to bot, wait for reply, return (reply_text, has_voice)."""
    bot = await client.get_entity(BOT_USERNAME)
    t0 = time.monotonic()
    msg_id = (await client.send_message(bot, text)).id
    print(f"\n{'='*60}")
    print(f"TEST {label}: sent '{text}' (msg_id={msg_id})")
    print(f"  waiting for reply (timeout={TIMEOUT}s)...")

    deadline = t0 + TIMEOUT
    last_print = t0
    while time.monotonic() < deadline:
        # Check for messages FROM bot TO us, newer than our sent message
        async for m in client.iter_messages(bot, limit=5, offset_date=None, reverse=False):
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
                    elif isinstance(m.media, MessageMediaPhoto):
                        media_type = "photo"
                    else:
                        media_type = str(type(m.media).__name__)

                text_preview = (m.text or "")[:200]
                print(f"  REPLY ({elapsed:.1f}s): text={text_preview!r}")
                print(f"  media_type={media_type} has_voice={has_voice}")
                if m.file:
                    print(f"  file_size={m.file.size if hasattr(m.file, 'size') else '?'} bytes")
                return text_preview, has_voice, media_type
        # Progress dot
        now = time.monotonic()
        if now - last_print > 10:
            print(f"  still waiting... ({now - t0:.0f}s)")
            last_print = now
        await asyncio.sleep(1)

    print(f"  TIMEOUT after {TIMEOUT}s — no reply received")
    return "", False, None


async def main():
    print(f"[TELETHON] Connecting as user (session: {SESSION})")
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"[TELETHON] Logged in as {me.first_name} (id={me.id})")

    results = {}

    # TEST A — normal text
    r_text, r_voice, r_media = await send_and_wait(client, "Hello KIO", "A-TEXT")
    results["A"] = {
        "sent": "Hello KIO",
        "reply": r_text,
        "has_voice": r_voice,
        "media": r_media,
        "pass": bool(r_text and not r_voice),
    }

    # Brief pause between tests
    await asyncio.sleep(3)

    # TEST B — referential voice
    r_text, r_voice, r_media = await send_and_wait(client, "Say that out loud", "B-REFERENTIAL")
    no_cant_speak = "can't physically" not in r_text.lower() and "cannot say" not in r_text.lower()
    results["B"] = {
        "sent": "Say that out loud",
        "reply": r_text,
        "has_voice": r_voice,
        "media": r_media,
        "no_fake_disclaimer": no_cant_speak,
        "pass": r_voice and no_cant_speak,
    }

    await asyncio.sleep(3)

    # TEST C — explicit voice request
    r_text, r_voice, r_media = await send_and_wait(
        client, "Give me a voice reply on Teachers Day", "C-EXPLICIT-VOICE"
    )
    results["C"] = {
        "sent": "Give me a voice reply on Teachers Day",
        "reply": r_text,
        "has_voice": r_voice,
        "media": r_media,
        "pass": r_voice,
    }

    await asyncio.sleep(3)

    # TEST D — simple text question (verify pipeline is alive)
    r_text, r_voice, r_media = await send_and_wait(
        client, "What is 2 + 2?", "D-MATH"
    )
    has_four = "4" in r_text
    results["D"] = {
        "sent": "What is 2 + 2?",
        "reply": r_text,
        "has_voice": r_voice,
        "media": r_media,
        "correct_answer": has_four,
        "pass": has_four,
    }

    # Print summary
    print(f"\n{'='*60}")
    print("VOICE ACCEPTANCE SUMMARY")
    print(f"{'='*60}")
    for k, v in results.items():
        status = "PASS" if v["pass"] else "FAIL"
        print(f"  TEST {k}: {status}")
        for fk, fv in v.items():
            if fk != "pass":
                print(f"    {fk}: {fv!r}")
    print(f"{'='*60}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
