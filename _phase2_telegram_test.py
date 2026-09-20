"""Phase 2 — Live Telegram Validation Script.
Sends real messages to KIO_Runtime_bot via Telethon user session.
Measures response latency and validates behavior.
"""
import asyncio
import time
import json
import os
import sys

TELEGRAM_API_ID = int(os.environ.get("TELEGRAM_API_ID", "39912440"))
TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH", "b62d46342966040767fa6660857caa31")
BOT_USERNAME = "KIO_Runtime_bot"
SESSION_FILE = "kio_user_session"
RESULTS = []

async def run_tests():
    from telethon import TelegramClient

    client = TelegramClient(SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"[USER] Logged in as: {me.first_name} (ID: {me.id})")

    bot = await client.get_entity(BOT_USERNAME)
    print(f"[BOT] Found: @{bot.username} (ID: {bot.id})")

    # Clear any pending messages first
    print("[SETUP] Clearing pending messages...")
    await client.send_read_acknowledge(bot)

    # Test A: Basic response
    print("\n=== TEST A: BASIC RESPONSE ===")
    t0 = time.time()
    msg = await client.send_message(bot, "hello")
    latency_a = None
    response_a = None
    for _ in range(60):
        await asyncio.sleep(1)
        history = await client.get_messages(bot, limit=5)
        for m in history:
            if m.outgoing and m.text == "hello":
                continue
            if not m.outgoing and m.date.timestamp() > t0:
                latency_a = time.time() - t0
                response_a = m.text
                break
        if response_a:
            break
    if response_a:
        print(f"  Response: {response_a[:200]}")
        print(f"  Latency: {latency_a:.2f}s")
        RESULTS.append({"test": "A_basic", "pass": True, "latency": latency_a, "response": response_a[:200]})
    else:
        print("  FAIL: No response within 60s")
        RESULTS.append({"test": "A_basic", "pass": False, "latency": None, "response": None})

    await asyncio.sleep(2)

    # Test B: Multiple rapid requests
    print("\n=== TEST B: RAPID REQUESTS (5 messages) ===")
    rapid_msgs = []
    t0 = time.time()
    for i in range(5):
        text = f"rapid test {i+1}"
        msg = await client.send_message(bot, text)
        rapid_msgs.append({"text": text, "sent_at": time.time() - t0, "msg_id": msg.id})
        await asyncio.sleep(0.3)
    print(f"  Sent 5 messages in {time.time()-t0:.2f}s")
    
    # Wait for responses
    await asyncio.sleep(30)
    history = await client.get_messages(bot, limit=20)
    responses = [m for m in history if not m.outgoing and m.date.timestamp() > t0 - 2]
    print(f"  Got {len(responses)} responses")
    for r in responses[:5]:
        print(f"    -> {r.text[:150]}")
    RESULTS.append({
        "test": "B_rapid",
        "pass": len(responses) >= 1,
        "sent": 5,
        "received": len(responses),
    })

    await asyncio.sleep(2)

    # Test C: Concurrent requests
    print("\n=== TEST C: CONCURRENT REQUESTS (4 messages) ===")
    t0 = time.time()
    tasks = []
    for i in range(4):
        text = f"concurrent test {i+1}"
        tasks.append(client.send_message(bot, text))
    sent = await asyncio.gather(*tasks)
    print(f"  Sent 4 messages concurrently in {time.time()-t0:.2f}s")
    
    await asyncio.sleep(30)
    history = await client.get_messages(bot, limit=20)
    responses = [m for m in history if not m.outgoing and m.date.timestamp() > t0 - 2]
    print(f"  Got {len(responses)} responses")
    for r in responses[:6]:
        print(f"    -> {r.text[:150]}")
    RESULTS.append({
        "test": "C_concurrent",
        "pass": len(responses) >= 1,
        "sent": 4,
        "received": len(responses),
    })

    await asyncio.sleep(2)

    # Test D: Informational response (stale-discard eligible)
    print("\n=== TEST D: INFORMATIONAL/STALE RESPONSE ===")
    t0 = time.time()
    await client.send_message(bot, "what's playing right now?")
    response_d = None
    for _ in range(60):
        await asyncio.sleep(1)
        history = await client.get_messages(bot, limit=5)
        for m in history:
            if not m.outgoing and m.date.timestamp() > t0:
                response_d = m.text
                latency_d = time.time() - t0
                break
        if response_d:
            break
    if response_d:
        print(f"  Response: {response_d[:200]}")
        print(f"  Latency: {latency_d:.2f}s")
        is_informational = any(kw in response_d.lower() for kw in ["nothing", "not playing", "no music", "not currently", "no active"])
        print(f"  Informational (eligible for stale-discard): {is_informational}")
        RESULTS.append({"test": "D_informational", "pass": True, "informational": is_informational, "response": response_d[:200]})
    else:
        print("  FAIL: No response within 60s")
        RESULTS.append({"test": "D_informational", "pass": False})

    await asyncio.sleep(2)

    # Test E: Recovery - send invalid command, then valid one
    print("\n=== TEST E: RECOVERY (invalid then valid) ===")
    t0_bad = time.time()
    await client.send_message(bot, "asdfghjkl invalid nonsense command 12345")
    await asyncio.sleep(10)
    history_bad = await client.get_messages(bot, limit=5)
    bad_responses = [m for m in history_bad if not m.outgoing and m.date.timestamp() > t0_bad]
    print(f"  Got {len(bad_responses)} response(s) to invalid input")
    for r in bad_responses[:2]:
        print(f"    -> {r.text[:150]}")
    
    await asyncio.sleep(2)
    t0_good = time.time()
    await client.send_message(bot, "hello")
    good_response = None
    for _ in range(60):
        await asyncio.sleep(1)
        history = await client.get_messages(bot, limit=5)
        for m in history:
            if not m.outgoing and m.date.timestamp() > t0_good:
                good_response = m.text
                break
        if good_response:
            break
    if good_response:
        print(f"  Recovery response: {good_response[:200]}")
        RESULTS.append({"test": "E_recovery", "pass": True, "response": good_response[:200]})
    else:
        print("  FAIL: No recovery response")
        RESULTS.append({"test": "E_recovery", "pass": False})

    # Summary
    print("\n" + "=" * 60)
    print("PHASE 2 TELEGRAM VALIDATION SUMMARY")
    print("=" * 60)
    for r in RESULTS:
        status = "PASS" if r.get("pass") else "FAIL"
        print(f"  {r['test']}: {status}", end="")
        if "latency" in r and r["latency"]:
            print(f" (latency: {r['latency']:.2f}s)", end="")
        if "received" in r:
            print(f" (sent={r['sent']}, recv={r['received']})", end="")
        print()
    
    passed = sum(1 for r in RESULTS if r.get("pass"))
    total = len(RESULTS)
    print(f"\n  Total: {passed}/{total} passed")

    # Write results to file for later
    with open("_phase2_results.json", "w") as f:
        json.dump(RESULTS, f, indent=2)

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(run_tests())
