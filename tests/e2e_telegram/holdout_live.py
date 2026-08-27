#!/usr/bin/env python3
"""Minimal 8-message E2E holdout — one at a time, real Telegram."""
from __future__ import annotations
import asyncio, json, os, sys, time
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
SESSION = os.path.join(ROOT, ".telegram_sessions", "kio_test_user.session")

TURNS = [
    ("A1", "identity", "yo KIO, what do you actually know about me?"),
    ("B1", "comm_style", "How do I usually want you to communicate with me?"),
    ("C1", "frustration", "What tends to piss me off when we're building KIO?"),
    ("D1", "corrections", "What have I repeatedly corrected you about?"),
    ("E1", "reversal", "What have I changed my mind about over time?"),
    ("F1", "dropped", "What projects or ideas have I dropped, paused, or moved away from?"),
    ("G1", "kio_self", "What do you know about yourself and how you've evolved?"),
    ("H1", "continuity", "What were we just talking about?"),
]

async def get_bot_username(client):
    import httpx
    async with httpx.AsyncClient(timeout=10) as http:
        r = await http.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
        return r.json()["result"]["username"]

async def send_and_wait(client, bot_entity, me_id, message, last_msg_id, timeout=60):
    start = time.time()
    sent = await client.send_message(bot_entity, message)
    sent_id = sent.id
    reply_text = None
    reply_id = None
    while time.time() - start < timeout:
        await asyncio.sleep(2.0)
        try:
            msgs = await client.get_messages(bot_entity, limit=10, min_id=last_msg_id or 0)
            for m in msgs:
                if m.sender_id != me_id and m.text and m.id > sent_id:
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

async def run():
    from telethon import TelegramClient
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    me_id = me.id
    bot_username = await get_bot_username(client)
    bot_entity = await client.get_entity(bot_username)
    print(f"Connected as {me.first_name} (id={me_id}), bot=@{bot_username}")
    print(f"{'='*60}")

    results = []
    last_msg_id = 0

    for tid, category, message in TURNS:
        print(f"\n[{tid}] [{category}] {message!r}")
        reply_text, reply_id, latency_ms = await send_and_wait(
            client, bot_entity, me_id, message, last_msg_id, timeout=60
        )
        last_msg_id = reply_id or last_msg_id

        if reply_text is None:
            status = "ERROR"
        elif reply_text.lower().startswith("media failed") or "keyerror" in reply_text.lower():
            status = "FAIL"
        elif len(reply_text.strip()) < 5:
            status = "FAIL"
        else:
            status = "PASS"

        preview = (reply_text or "(no reply)")[:150].replace("\n", " ")
        print(f"  [{status}] {latency_ms:.0f}ms | {preview}")

        results.append({
            "id": tid, "category": category, "message": message,
            "reply": reply_text, "latency_ms": latency_ms, "status": status,
        })
        await asyncio.sleep(2.0)

    await client.disconnect()

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")
    print(f"\n{'='*60}")
    print(f"RESULT: {passed} passed, {failed} failed, {errors} errors / {len(results)} total")
    print(f"{'='*60}")

    out = os.path.join(ROOT, "tests", "e2e_telegram", "holdout_live_result.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"metadata": {"started_at": datetime.now(timezone.utc).isoformat()}, "turns": results,
                    "summary": {"total": len(results), "passed": passed, "failed": failed, "errors": errors}}, f, indent=2, ensure_ascii=False)
    print(f"Transcript: {out}")

if __name__ == "__main__":
    asyncio.run(run())
