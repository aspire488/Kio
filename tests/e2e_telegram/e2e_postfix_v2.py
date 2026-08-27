import sys
sys.stdout.reconfigure(encoding="utf-8")
"""E2E Telegram driver — post-fix validation with unseen phrasing."""
import asyncio
import json
import os
import time
from dotenv import load_dotenv
load_dotenv()
from telethon import TelegramClient

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "KIO_Runtime_bot")
SESSION_FILE = os.getenv("TELETHON_SESSION", ".telegram_sessions/kio_test_user.session")

TESTS = [
    ("01", "greeting", "Good morning KIO", 15),
    ("02", "capability", "What can you actually help me with right now?", 45),
    ("03", "architecture", "How is your system actually put together?", 30),
    ("04", "arch_follow", "Go back to what you said about your architecture", 30),
    ("05", "personal", "Tell me about myself", 45),
    ("06", "runtime", "How is the machine doing right now?", 20),
    ("07", "ram", "How much RAM are you using at this moment?", 20),
    ("08", "capability_recall", "What did you just tell me you could do?", 20),
    ("09", "topic_return", "Going back to the system design thing", 30),
    ("10", "waiting_user", "What am I waiting on?", 20),
    ("11", "waiting_kio", "Are you waiting on anything from me?", 20),
    ("12", "identity", "Who exactly are you?", 15),
    ("13", "llm_identity", "Are you an LLM?", 15),
    ("14", "different_chatbot", "How are you different from an ordinary chatbot?", 20),
    ("15", "first_message", "What was the very first thing I said to you in this chat?", 20),
    ("16", "patterns", "What patterns have you noticed about me?", 30),
    ("17", "casual", "Thanks KIO, that is all for now", 15),
]

async def main():
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"Driver: {me.first_name} (ID: {me.id})")
    bot = await client.get_entity(BOT_USERNAME)
    transcript = []
    for tid, category, message, timeout in TESTS:
        print(f"\n--- [{tid}] {category} ---")
        print(f"  Send: {message!r}")
        t0 = time.monotonic()
        try:
            sent = await client.send_message(bot, message)
            user_msg_id = sent.id
        except Exception as e:
            print(f"  SEND FAILED: {e}")
            transcript.append({"id": tid, "category": category, "message": message, "error": str(e), "status": "SEND_FAILED"})
            continue
        reply_text = None
        bot_msg_id = None
        deadline = time.monotonic() + timeout
        seen_ids = set()
        while time.monotonic() < deadline:
            await asyncio.sleep(1.5)
            async for msg in client.iter_messages(bot, limit=10):
                if msg.id <= user_msg_id:
                    continue
                if msg.id in seen_ids:
                    continue
                seen_ids.add(msg.id)
                if msg.text and not msg.text.startswith("/"):
                    reply_text = msg.text
                    bot_msg_id = msg.id
                    break
            if reply_text:
                break
        latency = round(time.monotonic() - t0, 1)
        if reply_text:
            print(f"  Reply ({latency}s): {reply_text[:120]!r}")
            transcript.append({"id": tid, "category": category, "message": message, "reply": reply_text, "latency_s": latency, "user_msg_id": user_msg_id, "bot_msg_id": bot_msg_id, "status": "PASS"})
        else:
            print(f"  NO REPLY within {timeout}s")
            transcript.append({"id": tid, "category": category, "message": message, "latency_s": latency, "status": "TIMEOUT"})
        await asyncio.sleep(2)
    passed = sum(1 for t in transcript if t["status"] == "PASS")
    total = len(transcript)
    print(f"\n{'='*60}")
    print(f"RESULT: {passed}/{total} passed")
    for t in transcript:
        s = "PASS" if t["status"] == "PASS" else "FAIL"
        print(f"  [{t['id']}] {s} {t['category']}: {t.get('reply', 'NO REPLY')[:80]}")
    out = "tests/e2e_telegram/transcript_postfix_v2.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)
    print(f"\nTranscript: {out}")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
