"""Phase 2 — Live Telegram Validation.
Uses kio_test_user session to send real messages to KIO_Runtime_bot.
"""
import asyncio
import time
import json
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

TELEGRAM_API_ID = 39912440
TELEGRAM_API_HASH = "b62d46342966040767fa6660857caa31"
BOT_USERNAME = "KIO_Runtime_bot"
SESSION = ".telegram_sessions/kio_test_user"
RESULTS = []
BOT_ID = None
MY_ID = None

def is_from_bot(m):
    return m.sender_id == BOT_ID

def is_from_me(m):
    return m.sender_id == MY_ID

async def wait_for_bot_response(client, bot_entity, after_ts, timeout=90):
    for _ in range(timeout):
        await asyncio.sleep(2)
        history = await client.get_messages(bot_entity, limit=10)
        for m in history:
            if is_from_bot(m) and m.date.timestamp() > after_ts:
                return m
    return None

async def count_bot_responses(client, bot_entity, after_ts, limit=20):
    history = await client.get_messages(bot_entity, limit=limit)
    return [m for m in history if is_from_bot(m) and m.date.timestamp() > after_ts]

async def run_tests():
    global BOT_ID, MY_ID
    from telethon import TelegramClient

    client = TelegramClient(SESSION, TELEGRAM_API_ID, TELEGRAM_API_HASH)
    await client.start()
    me = await client.get_me()
    MY_ID = me.id
    print(f"[USER] Logged in as: {me.first_name} (ID: {me.id})")

    bot_entity = await client.get_entity(BOT_USERNAME)
    BOT_ID = bot_entity.id
    print(f"[BOT] Found: @{bot_entity.username} (ID: {BOT_ID})")

    await client.send_read_acknowledge(bot_entity)
    await asyncio.sleep(2)

    # ============================================
    # TEST A: BASIC RESPONSE
    # ============================================
    print("\n" + "="*60)
    print("TEST A: BASIC RESPONSE")
    print("="*60)
    t0 = time.time()
    await client.send_message(bot_entity, "hello")
    resp = await wait_for_bot_response(client, bot_entity, t0, timeout=90)
    if resp:
        latency = resp.date.timestamp() - t0
        print(f"  Response: {resp.text[:300]}")
        print(f"  Latency: {latency:.2f}s")
        RESULTS.append({"test": "A_basic_response", "pass": True, "latency": round(latency, 2), "response_len": len(resp.text)})
    else:
        print("  FAIL: No response within 90s")
        RESULTS.append({"test": "A_basic_response", "pass": False})

    await asyncio.sleep(3)

    # ============================================
    # TEST B: MULTIPLE RAPID REQUESTS (5 messages)
    # ============================================
    print("\n" + "="*60)
    print("TEST B: MULTIPLE RAPID REQUESTS (5 messages)")
    print("="*60)
    t0 = time.time()
    for i in range(5):
        await client.send_message(bot_entity, f"what time is it?")
        await asyncio.sleep(1)
    print(f"  Sent 5 messages in {time.time()-t0:.2f}s")

    await asyncio.sleep(60)
    responses = await count_bot_responses(client, bot_entity, t0)
    print(f"  Got {len(responses)} responses")
    for r in responses[:6]:
        print(f"    -> [{r.date.strftime('%H:%M:%S')}] {r.text[:150]}")
    RESULTS.append({"test": "B_rapid_requests", "pass": len(responses) >= 1, "sent": 5, "received": len(responses)})

    await asyncio.sleep(3)

    # ============================================
    # TEST C: CONCURRENT REQUESTS (4 at once)
    # ============================================
    print("\n" + "="*60)
    print("TEST C: CONCURRENT REQUESTS (4 at once)")
    print("="*60)
    t0 = time.time()
    tasks = [client.send_message(bot_entity, f"hello test concurrent {i+1}") for i in range(4)]
    await asyncio.gather(*tasks)
    print(f"  Sent 4 messages concurrently in {time.time()-t0:.2f}s")

    await asyncio.sleep(60)
    responses = await count_bot_responses(client, bot_entity, t0)
    print(f"  Got {len(responses)} responses")
    for r in responses[:6]:
        print(f"    -> [{r.date.strftime('%H:%M:%S')}] {r.text[:150]}")
    RESULTS.append({"test": "C_concurrent_4", "pass": len(responses) >= 1, "sent": 4, "received": len(responses)})

    await asyncio.sleep(3)

    # ============================================
    # TEST D: INFORMATIONAL / STALE-DISCARD ELIGIBLE
    # ============================================
    print("\n" + "="*60)
    print("TEST D: INFORMATIONAL RESPONSE (stale-discard eligible)")
    print("="*60)
    t0 = time.time()
    await client.send_message(bot_entity, "what's playing right now")
    resp = await wait_for_bot_response(client, bot_entity, t0, timeout=90)
    if resp:
        latency = resp.date.timestamp() - t0
        print(f"  Response: {resp.text[:300]}")
        print(f"  Latency: {latency:.2f}s")
        is_informational = any(kw in resp.text.lower() for kw in [
            "nothing", "not playing", "no music", "not currently",
            "no active", "nothing is", "no song", "nothing's"
        ])
        print(f"  Informational (stale-discard eligible): {is_informational}")
        RESULTS.append({"test": "D_informational_stale_eligible", "pass": True, "informational": is_informational, "latency": round(latency, 2)})
    else:
        print("  FAIL: No response within 90s")
        RESULTS.append({"test": "D_informational_stale_eligible", "pass": False})

    await asyncio.sleep(3)

    # ============================================
    # TEST E: RECOVERY (invalid then valid)
    # ============================================
    print("\n" + "="*60)
    print("TEST E: RECOVERY (invalid then valid)")
    print("="*60)
    t0_bad = time.time()
    await client.send_message(bot_entity, "asdfghjkl12345 invalid_command_xyz")
    await asyncio.sleep(10)

    t0_good = time.time()
    await client.send_message(bot_entity, "hello")
    resp = await wait_for_bot_response(client, bot_entity, t0_good, timeout=90)
    if resp:
        latency = resp.date.timestamp() - t0_good
        print(f"  Recovery response: {resp.text[:200]}")
        print(f"  Recovery latency: {latency:.2f}s")
        RESULTS.append({"test": "E_recovery", "pass": True, "latency": round(latency, 2)})
    else:
        print("  FAIL: No recovery response")
        RESULTS.append({"test": "E_recovery", "pass": False})

    # ============================================
    # SUMMARY
    # ============================================
    print("\n" + "="*60)
    print("PHASE 2 TELEGRAM VALIDATION SUMMARY")
    print("="*60)
    for r in RESULTS:
        status = "PASS" if r.get("pass") else "FAIL"
        extra = ""
        if "latency" in r and r["latency"]:
            extra += f" latency={r['latency']}s"
        if "received" in r:
            extra += f" sent={r['sent']} recv={r['received']}"
        if "informational" in r:
            extra += f" informational={r['informational']}"
        print(f"  {r['test']}: {status}{extra}")

    passed = sum(1 for r in RESULTS if r.get("pass"))
    total = len(RESULTS)
    print(f"\n  Total: {passed}/{total} passed")

    with open("_phase2_results.json", "w") as f:
        json.dump(RESULTS, f, indent=2)

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(run_tests())
