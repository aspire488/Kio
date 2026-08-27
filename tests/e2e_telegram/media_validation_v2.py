"""
Live media validation from Joel's real Telegram account -> KIO bot.
Sends messages sequentially and captures responses.
"""
import asyncio
import json
import time
import sys
import os
import codecs

# Fix Windows console encoding for Unicode output
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from telethon import TelegramClient

API_ID = 20488284
API_HASH = "9265e20bf04084af1d7dc8fbb37ba074"
SESSION = ".telegram_sessions/kio_test_user"
KIO_BOT = "@KIO_Runtime_bot"

# Forbidden strings that must never appear in media responses
FORBIDDEN_MEDIA = [
    "popular songs", "popular music", "trending music", "top tracks",
    "good music", "viral video", "popular video", "something interesting",
    "playing popular", "going with popular",
]

TEST_MATRIX = [
    {"id": "M1", "msg": "play something", "desc": "Cold start discovery"},
    {"id": "M2", "msg": "nah", "desc": "Rejection 1"},
    {"id": "M3", "msg": "nah", "desc": "Rejection 2"},
    {"id": "M4", "msg": "what is playing?", "desc": "Now playing"},
    {"id": "M5", "msg": "pause", "desc": "Pause"},
    {"id": "M6", "msg": "resume", "desc": "Resume"},
    {"id": "M7", "msg": "stop", "desc": "Stop"},
    {"id": "M8", "msg": "play something from Karikku", "desc": "Explicit creator request"},
    {"id": "M9", "msg": "play something funny", "desc": "Mood-based discovery"},
    {"id": "M10", "msg": "another one", "desc": "Continuation"},
    {"id": "M11", "msg": "nah", "desc": "Rejection after continuation"},
    {"id": "M12", "msg": "play something", "desc": "Generic after preferences established"},
    {"id": "M13", "msg": "Happy Onam", "desc": "Social request"},
    {"id": "M14", "msg": "I am bored", "desc": "Boredom (should NOT auto-trigger media)"},
    {"id": "M15", "msg": "why is the sky blue?", "desc": "Knowledge question"},
]


async def main():
    client = TelegramClient(SESSION, api_id=API_ID, api_hash=API_HASH)
    await client.start()

    me = await client.get_me()
    print("=== SENDER ACCOUNT ===")
    print(f"Name: {me.first_name} {me.last_name or ''}")
    print(f"ID: {me.id}")
    print("=== END SENDER ===")
    print()

    # Resolve bot entity and get bot's ID to filter messages
    bot_entity = await client.get_entity(KIO_BOT)
    KIO_BOT_ID = bot_entity.id
    print(f"Bot entity ID: {KIO_BOT_ID}")
    print()

    results = []

    for test in TEST_MATRIX:
        test_id = test["id"]
        msg = test["msg"]
        desc = test["desc"]

        print(f"[{test_id}] {desc}")
        print(f"  Sending: {msg}")

        start_time = time.time()

        # Send message from Joel to KIO bot
        try:
            sent = await client.send_message(bot_entity, msg)
            sent_ts = sent.date.timestamp() if sent.date else time.time()
            print(f"  Sent at: {time.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"  ERROR sending: {e}")
            results.append({"id": test_id, "msg": msg, "desc": desc, "response": f"ERROR: {e}", "latency": "0s", "forbidden": [], "status": "ERROR"})
            continue

        # Wait for bot response
        response_text = ""
        response_time = 0
        max_wait = 90

        try:
            await asyncio.sleep(3)
            deadline = time.time() + max_wait
            found_response = False

            while time.time() < deadline:
                # Get recent messages from the bot chat
                async for message in client.iter_messages(bot_entity, limit=10):
                    # Must be from the bot (sender_id == bot), not from Joel
                    if message.sender_id != KIO_BOT_ID:
                        continue
                    # Must be after our sent message
                    if message.date and message.date.timestamp() > sent_ts:
                        if message.text and not message.text.startswith("["):
                            response_text = message.text
                            response_time = time.time() - start_time
                            found_response = True
                            break
                if found_response:
                    break
                await asyncio.sleep(2)

        except Exception as e:
            print(f"  ERROR waiting: {e}")
            response_text = f"ERROR: {e}"

        # Check forbidden strings
        forbidden_found = []
        resp_lower = response_text.lower()
        for f in FORBIDDEN_MEDIA:
            if f in resp_lower:
                forbidden_found.append(f)

        latency = f"{response_time:.1f}s" if response_time > 0 else "timeout"
        status = "PASS" if not forbidden_found else "FAIL"

        print(f"  Response ({latency}): {response_text[:200]}")
        if forbidden_found:
            print(f"  FORBIDDEN strings: {forbidden_found}")
        print(f"  Status: {status}")
        print()

        results.append({
            "id": test_id,
            "msg": msg,
            "desc": desc,
            "response": response_text,
            "latency": latency,
            "forbidden": forbidden_found,
            "status": status,
        })

        await asyncio.sleep(1)

    # Save transcript
    transcript_path = "tests/e2e_telegram/media_validation_v2_transcript.json"
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=False)

    # Summary
    print()
    print("=" * 60)
    print("LIVE VALIDATION SUMMARY")
    print("=" * 60)
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = total - passed

    for r in results:
        icon = "PASS" if r["status"] == "PASS" else "FAIL"
        resp_short = r["response"][:80].replace("\n", " ")
        print(f"  [{icon}] [{r['id']}] {r['desc']}: {resp_short}")

    print(f"\nTotal: {passed}/{total} passed, {failed} failed")

    if failed > 0:
        print("\nFAILED TESTS:")
        for r in results:
            if r["status"] != "PASS":
                print(f"  [{r['id']}] {r['desc']}")
                print(f"    Forbidden: {r['forbidden']}")
                print(f"    Response: {r['response'][:300]}")

    await client.disconnect()
    return results


if __name__ == "__main__":
    results = asyncio.run(main())
