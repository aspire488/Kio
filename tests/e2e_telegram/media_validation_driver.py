#!/usr/bin/env python3
"""
Live Media Validation Driver — Joel's Real Telegram Account

Sends messages FROM Joel's user account TO the KIO bot.
Captures responses and verifies media discovery behavior.
"""
from __future__ import annotations
import asyncio, json, os, sys, time
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final"
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
SESSION = os.path.join(ROOT, ".telegram_sessions", "kio_test_user.session")
ALLOWED_USER_ID = 2146008061

# Media validation test matrix
MEDIA_TESTS = [
    # (test_id, category, message, max_wait_s)
    ("M1", "cold_start", "play something", 90),
    ("M2", "rejection_1", "nah", 90),
    ("M3", "rejection_2", "nah", 90),
    ("M4", "now_playing", "what is playing?", 30),
    ("M5", "transport_pause", "pause", 15),
    ("M6", "transport_resume", "resume", 15),
    ("M7", "transport_stop", "stop", 15),
    # Continuation test
    ("M8", "contextual_discovery", "play something funny", 90),
    ("M9", "continuation", "another one", 90),
    # Non-media regression
    ("M10", "regression_social", "Happy Onam", 30),
    ("M11", "regression_boredom", "I am bored", 30),
    ("M12", "regression_knowledge", "why is the sky blue?", 30),
]

# Hardcoded strings that must NEVER appear in responses
FORBIDDEN_STRINGS = [
    "popular songs", "popular music", "trending music",
    "top tracks", "viral video", "popular video",
    "something interesting", "good music to listen to",
]

async def get_bot_username(client):
    import httpx
    async with httpx.AsyncClient(timeout=10) as http:
        r = await http.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
        return r.json()["result"]["username"]

async def send_and_wait(client, bot_entity, me_id, message, last_msg_id, timeout=60):
    """Send a message and wait for bot response."""
    start = time.time()
    sent = await client.send_message(bot_entity, message)
    sent_id = sent.id
    reply_text = None
    reply_id = None
    while time.time() - start < timeout:
        await asyncio.sleep(2.0)
        try:
            msgs = await client.get_messages(bot_entity, limit=10, min_id=sent_id)
            for m in msgs:
                if m.sender_id != me_id and m.text:
                    reply_text = m.text
                    reply_id = m.id
                    last_msg_id = m.id
                    break
            if reply_text:
                break
        except Exception as exc:
            print(f"  [WARN] fetch: {exc}", file=sys.stderr)
            await asyncio.sleep(1)
    latency_ms = round((time.time() - start) * 1000, 1)
    return reply_text, reply_id, latency_ms

def check_forbidden(reply_text: str) -> list:
    """Check if response contains any forbidden hardcoded strings."""
    found = []
    if reply_text:
        lower = reply_text.lower()
        for fs in FORBIDDEN_STRINGS:
            if fs in lower:
                found.append(fs)
    return found

async def run_media_validation():
    """Run the full media validation test matrix."""
    from telethon import TelegramClient

    transcript = {
        "metadata": {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "bot_token_prefix": BOT_TOKEN[:8] if BOT_TOKEN else "NONE",
            "validation_type": "live_media_discovery",
        },
        "turns": [],
        "summary": {},
        "forbidden_violations": [],
    }

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        transcript["error"] = "telethon_not_authorized"
        await client.disconnect()
        print("ERROR: Telethon not authorized. Need to run auth first.")
        return transcript

    me = await client.get_me()
    bot_username = await get_bot_username(client)
    bot_entity = f"@{bot_username}"

    print(f"\n{'='*60}")
    print(f"KIO LIVE MEDIA VALIDATION")
    print(f"{'='*60}")
    print(f"Bot: @{bot_username}")
    print(f"Driver: {me.first_name} (id={me.id})")
    print(f"Account: {'JOEL' if me.id == ALLOWED_USER_ID else 'UNKNOWN'}")
    print(f"Tests: {len(MEDIA_TESTS)}")
    print(f"{'='*60}\n")

    if me.id != ALLOWED_USER_ID:
        print(f"WARNING: Driver account ID {me.id} != expected {ALLOWED_USER_ID}")
        print("This may not be Joel's account!")

    last_msg_id = 0
    passed = failed = 0
    results = []
    all_violations = []

    for test_id, category, message, max_wait in MEDIA_TESTS:
        print(f"[{test_id}] [{category}] Sending: {message}")
        reply_text, reply_id, latency_ms = await send_and_wait(
            client, bot_entity, me.id, message, last_msg_id, max_wait
        )

        # Check for forbidden hardcoded strings
        violations = check_forbidden(reply_text or "")
        if violations:
            all_violations.extend([(test_id, v) for v in violations])
            print(f"  [VIOLATION] Forbidden strings found: {violations}")

        if reply_text is None:
            status = "FAIL"
            failed += 1
        elif reply_text.strip() == "":
            status = "FAIL"
            failed += 1
        else:
            status = "PASS"
            passed += 1

        preview = (reply_text or "(no reply)")[:120].replace("\n", " ")
        print(f"  [{status}] {latency_ms:.0f}ms | {preview}\n")

        turn_result = {
            "test_id": test_id,
            "category": category,
            "user_message": message,
            "bot_reply": reply_text or "(no reply)",
            "latency_ms": latency_ms,
            "status": status,
            "forbidden_violations": violations,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        results.append(turn_result)
        last_msg_id = reply_id or last_msg_id
        await asyncio.sleep(2)

    await client.disconnect()

    transcript["turns"] = results
    transcript["forbidden_violations"] = all_violations
    transcript["summary"] = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "forbidden_violations": len(all_violations),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    print(f"{'='*60}")
    print(f"SUMMARY: {passed} passed, {failed} failed / {len(results)} total")
    if all_violations:
        print(f"FORBIDDEN VIOLATIONS: {len(all_violations)}")
        for tid, v in all_violations:
            print(f"  [{tid}] '{v}'")
    else:
        print("FORBIDDEN VIOLATIONS: 0 (clean)")
    print(f"{'='*60}\n")

    return transcript

def main():
    transcript = asyncio.run(run_media_validation())
    transcript_path = os.path.join(ROOT, "tests", "e2e_telegram", "media_validation_transcript.json")
    os.makedirs(os.path.dirname(transcript_path), exist_ok=True)
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)
    print(f"Transcript saved: {transcript_path}")
    summary = transcript.get("summary", {})
    if summary.get("failed", 0) > 0 or summary.get("forbidden_violations", 0) > 0:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
