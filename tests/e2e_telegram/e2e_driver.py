#!/usr/bin/env python3
"""Automated Telegram E2E validation driver for KIO Companion Intelligence."""
from __future__ import annotations
import argparse, asyncio, json, os, sys, time
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

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

TEST_CONVERSATION = [
    ("A1", "normal_conversation", "What is KIO?", 45),
    ("B1", "continuity", "What kind of things can you actually do?", 45),
    ("B2", "continuity", "What is the weather like today?", 30),
    ("B3", "continuity", "Going back to what you said about capabilities, what is your most important one?", 45),
    ("C1", "personal_context", "What do you know about me?", 45),
    ("C2", "personal_context", "What am I currently studying?", 30),
    ("C3", "personal_context", "What have I been working on lately?", 45),
    ("D1", "kio_identity", "Are you just a chatbot?", 45),
    ("E1", "runtime_awareness", "KIO health", 30),
    ("E2", "runtime_awareness", "How much RAM am I using?", 30),
    ("G1", "personality", "What do you think about AI replacing developers?", 45),
    ("H1", "response_continuity", "Tell me about the KIO project architecture and what makes it different from a regular chatbot", 60),
    ("I1", "continuity_recall", "What were we discussing earlier about your capabilities?", 45),
    ("J1", "normal_conversation", "Thanks KIO, that is all for now", 30),
]

async def get_bot_username(client):
    import httpx
    async with httpx.AsyncClient(timeout=10) as http:
        r = await http.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
        return r.json()["result"]["username"]

async def send_and_wait(client, bot_entity, me_id, message, last_msg_id, timeout=45):
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

async def run_e2e(timeout_per_message=60):
    transcript = {
        "metadata": {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "bot_token_prefix": BOT_TOKEN[:8] if BOT_TOKEN else "NONE",
        },
        "turns": [],
        "summary": {},
    }
    from telethon import TelegramClient
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        transcript["error"] = "telethon_not_authorized"
        await client.disconnect()
        return transcript
    me = await client.get_me()
    bot_username = await get_bot_username(client)
    bot_entity = f"@{bot_username}"
    transcript["metadata"]["bot_username"] = bot_username
    transcript["metadata"]["telethon_user_id"] = me.id

    print(f"\n{'='*60}")
    print(f"KIO TELEGRAM E2E -- Automated Validation")
    print(f"{'='*60}")
    print(f"Bot: @{bot_username}")
    print(f"Driver: {me.first_name} (id={me.id})")
    print(f"Turns: {len(TEST_CONVERSATION)}")
    print(f"{'='*60}\n")

    last_msg_id = 0
    passed = failed = errors = 0
    results = []
    for test_id, category, message, max_wait in TEST_CONVERSATION:
        wait = min(max_wait, timeout_per_message)
        print(f"[{test_id}] [{category}] Sending: {message[:60]}...")
        reply_text, reply_id, latency_ms = await send_and_wait(
            client, bot_entity, me.id, message, last_msg_id, wait
        )
        if reply_text is None:
            status, reason, failed = "FAIL", "no_reply", failed + 1
        elif reply_text.strip() == "":
            status, reason, failed = "FAIL", "empty_reply", failed + 1
        elif "error" in reply_text.lower() and "still running" in reply_text.lower():
            status, reason, errors = "ERROR", "kio_error", errors + 1
        else:
            status, reason, passed = "PASS", "reply_received", passed + 1
        turn_result = {
            "test_id": test_id, "category": category,
            "user_message": message,
            "bot_reply": reply_text or "(no reply)",
            "latency_ms": latency_ms, "status": status,
            "status_reason": reason,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        results.append(turn_result)
        icon = "+" if status == "PASS" else ("X" if status == "FAIL" else "!")
        preview = (reply_text or "(no reply)")[:80].replace("\n", " ")
        print(f"  [{icon} {status}] {latency_ms:.0f}ms | {preview}\n")
        last_msg_id = reply_id or last_msg_id
        await asyncio.sleep(1.5)
    await client.disconnect()
    transcript["turns"] = results
    transcript["summary"] = {
        "total": len(results), "passed": passed,
        "failed": failed, "errors": errors,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    print(f"{'='*60}")
    print(f"SUMMARY: {passed} passed, {failed} failed, {errors} errors / {len(results)} total")
    print(f"{'='*60}\n")
    return transcript

def main():
    parser = argparse.ArgumentParser(description="KIO Telegram E2E driver")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--transcript", type=str, default=None)
    args = parser.parse_args()
    transcript = asyncio.run(run_e2e(timeout_per_message=args.timeout))
    transcript_path = args.transcript or os.path.join(ROOT, "tests", "e2e_telegram", "transcript.json")
    os.makedirs(os.path.dirname(transcript_path), exist_ok=True)
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)
    print(f"Transcript: {transcript_path}")
    summary = transcript.get("summary", {})
    if summary.get("failed", 0) > 0 or summary.get("errors", 0) > 0:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
