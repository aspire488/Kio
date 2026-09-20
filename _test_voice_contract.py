"""Live voice note test: send a voice note and verify text+voice response."""
import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
SESSION = ".telegram_sessions/kio_test_user.session"

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (ID: {me.id})")

    target = "KIO_Runtime_bot"

    # Send voice note
    voice_path = "_voice_test4_v2.ogg"
    if not os.path.exists(voice_path):
        print(f"FAIL: voice file not found: {voice_path}")
        return

    print(f"\nSending voice note: {voice_path} ({os.path.getsize(voice_path)} bytes)")
    t0 = time.monotonic()
    sent = await client.send_file(target, voice_path, voice_notes=True)
    print(f"Voice sent at {time.monotonic() - t0:.1f}s, msg_id={sent.id}")

    # Wait for reply (up to 45s)
    print("Waiting for KIO reply...")
    t1 = time.monotonic()
    got_text = False
    got_voice = False
    reply_text = ""
    while time.monotonic() - t1 < 45:
        await asyncio.sleep(2)
        msgs = await client.get_messages(target, limit=5)
        for msg in msgs:
            if msg.date and msg.date.timestamp() > t0 - 2 and msg.id > sent.id:
                elapsed = time.monotonic() - t1
                if msg.text and not got_text:
                    got_text = True
                    reply_text = msg.text
                    print(f"[{elapsed:.1f}s] TEXT reply: {reply_text!r}")
                if msg.voice and not got_voice:
                    got_voice = True
                    print(f"[{elapsed:.1f}s] VOICE reply received ({msg.voice.size} bytes)")
                if got_text and got_voice:
                    break
        if got_text and got_voice:
            break

    print(f"\n=== RESULTS ===")
    print(f"Text reply:  {'PASS' if got_text else 'FAIL (missing)'}")
    print(f"Voice reply: {'PASS' if got_voice else 'FAIL (missing)'}")
    if got_text and got_voice:
        print("CONTRACT: TEXT+VOICE from one canonical answer -- PASS")
    elif got_text and not got_voice:
        print("CONTRACT: text only, no voice -- FAIL")
    elif got_text is False:
        print("CONTRACT: no reply at all -- FAIL")
    await client.disconnect()

asyncio.run(main())
