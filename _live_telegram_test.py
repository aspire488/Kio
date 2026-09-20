import asyncio
import os
import time
import sys

from dotenv import load_dotenv
import telethon

load_dotenv(override=True)

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE = os.getenv("TELEGRAM_USER_PHONE")
SESSION = "kio_live_session"

MSG_TO_KIO = "Find some chill lo-fi hip hop on YouTube."
MAX_WAIT = 20.0


async def run():
    client = telethon.TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()

    try:
        if not await client.is_user_authorized():
            print("SESSION_NOT_AUTHORIZED", flush=True)
            await client.disconnect()
            return

        me = await client.get_entity("me")
        my_id = me.id
        print(f"AUTHED_USER_ID={my_id}", flush=True)

        # Locate KIO bot by scanning recent dialogs for a Telegram bot whose name suggests KIO.
        kio_entity = None
        async for dialog in client.iter_dialogs(limit=200):
            name = ""
            if dialog.entity:
                name = getattr(dialog.entity, "first_name", "") or ""
                if hasattr(dialog.entity, "username") and dialog.entity.username:
                    name = dialog.entity.username
            if name.lower().startswith("kio") or "kio" in name.lower():
                kio_entity = dialog.entity
                break

        if kio_entity is None:
            # fallback: try username @kio_bot if that exists
            try:
                kio_entity = await client.get_entity("kio_bot")
            except Exception:
                pass

        if kio_entity is None:
            print("KIO_BOT_NOT_FOUND", flush=True)
            await client.disconnect()
            return

        kio_id = kio_entity.id if hasattr(kio_entity, "id") else None
        print(f"FOUND_KIO_BOT_ID={kio_id}", flush=True)

        t0 = time.time()
        sent = await client.send_message(kio_entity, MSG_TO_KIO)
        send_ts = time.time()

        print(f"MSG_SENT_AT={send_ts} CHAT_ID={getattr(kio_entity,'id',None)}", flush=True)

        # Poll for the reply. Telethon can fetch updates via get_updates or polls via
        # iter_messages; we use a time-bounded read of the conversation history.
        got_reply = False
        reply_text = ""
        reply_ts = None
        deadline = send_ts + MAX_WAIT
        while time.time() < deadline:
            try:
                # read last 5 messages in the chat
                msgs = await client.get_messages(kio_entity, limit=5)
                for m in msgs:
                    if m and m.message and m.sender_id == my_id:
                        continue
                    if m and m.message and m.date:
                        if m.date >= time.time() - 0.1 and m.message:
                            reply_text = m.message.strip()
                            reply_ts = time.time()
                            got_reply = True
                            break
                if got_reply:
                    break
            except Exception as e:
                print(f"POLL_ERR={type(e).__name__}", flush=True)
            await asyncio.sleep(0.8)

        latency = (reply_ts - send_ts) if (reply_ts and got_reply) else (time.time() - send_ts)
        print(f"LATENCY={latency:.3f}", flush=True)
        print(f"GOT_REPLY={got_reply}", flush=True)
        print(f"REPLY_TEXT={reply_text}", flush=True)

    except Exception as e:
        print(f"FATAL={type(e).__name__}:{e}", flush=True)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as e:
        print(f"WRAPPER={type(e).__name__}:{e}", flush=True)
