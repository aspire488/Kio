#!/usr/bin/env python3
"""30-turn companion holdout — unseen phrasing, real Telegram."""
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
ALLOWED_USER_ID = 2146008061

# 30 turns — unseen phrasing, natural human language
TURNS = [
    # A. Natural conversation
    ("A1", "casual", "yo"),
    ("A2", "followup", "what were we talking about"),
    ("A3", "slang", "u good?"),
    ("A4", "topic_switch", "nah forget that tell me something else"),
    # B. Current personal state
    ("B1", "current", "what am I doing these days"),
    ("B2", "current", "what's my main focus right now"),
    ("B3", "current", "what projects are active"),
    # C. Longitudinal understanding
    ("C1", "comm_style", "how do I usually talk to you"),
    ("C2", "debug_behavior", "what am I like when debugging something"),
    ("C3", "frustration", "what tends to piss me off"),
    ("C4", "excitement", "what gets me hyped"),
    ("C5", "decision_style", "how do I make tech decisions"),
    ("C6", "decision_reversal", "what have I changed my mind on"),
    # D. KIO self-knowledge
    ("D1", "kio_self", "what do you know about yourself"),
    ("D2", "kio_learning", "what have you picked up from working with me"),
    ("D3", "kio_mistakes", "what do you keep getting wrong"),
    ("D4", "kio_boundaries", "what should you know not to do with me"),
    ("D5", "kio_evolution", "how have you changed"),
    # E. Deterministic system
    ("E1", "ram", "whats my ram usage"),
    ("E2", "cpu", "how's my cpu doing"),
    # F. Existing capabilities
    ("F1", "capabilities", "what can you actually do"),
    # G. Architecture
    ("G1", "architecture", "how is kio built"),
    ("G2", "memory", "how does your memory work"),
    # H. Conversational memory
    ("H1", "context_inject", "remember this number: 42"),
    ("H2", "context_recall", "what number did i just mention"),
    # I. Historical vs current
    ("I1", "abandoned", "what stuff have I completely dropped"),
    ("I2", "past", "what was I into months ago"),
    # J. KIO corrections
    ("J1", "corrections", "what have I had to correct you about"),
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
    passed = failed = errors = 0

    for tid, category, message in TURNS:
        print(f"\n[{tid}] [{category}] {message!r}")
        reply_text, reply_id, latency_ms = await send_and_wait(
            client, bot_entity, me_id, message, last_msg_id, timeout=60
        )
        last_msg_id = reply_id or last_msg_id

        if reply_text is None:
            status = "ERROR"
            reason = "no_reply"
            errors += 1
        elif reply_text.lower().startswith("media failed") or "keyerror" in reply_text.lower():
            status = "FAIL"
            reason = "routing_error"
            failed += 1
        elif len(reply_text.strip()) < 5:
            status = "FAIL"
            reason = "too_short"
            failed += 1
        else:
            status = "PASS"
            reason = "ok"
            passed += 1

        preview = (reply_text or "(no reply)")[:100].replace("\n", " ")
        print(f"  [{status}] {latency_ms:.0f}ms | {preview}")

        results.append({
            "id": tid, "category": category, "message": message,
            "reply": reply_text, "latency_ms": latency_ms,
            "status": status, "reason": reason,
        })
        await asyncio.sleep(1.5)

    await client.disconnect()

    print(f"\n{'='*60}")
    print(f"RESULT: {passed} passed, {failed} failed, {errors} errors / {len(results)} total")
    print(f"{'='*60}")

    transcript = {
        "metadata": {"started_at": datetime.now(timezone.utc).isoformat()},
        "turns": results,
        "summary": {"total": len(results), "passed": passed, "failed": failed, "errors": errors},
    }
    out = os.path.join(ROOT, "tests", "e2e_telegram", "holdout_final_result.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)
    print(f"Transcript: {out}")
    return transcript

if __name__ == "__main__":
    asyncio.run(run())
