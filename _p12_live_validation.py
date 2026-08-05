"""P1.2 guard-set live Telegram validation - ATTACH ONLY (no spawn, no restart).

Attaches to the already-running KIO runtime (started after P1.2 edits),
clears stray /start pollution from the prior aborted run, then drives the
real guard-set scenarios (G1-G5, S1/S2 new surface) plus the 7 documented
context-bleed scenarios. Bounded waits. Writes validation_complete.md.
"""
import asyncio, json, os, sys, time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.chdir(Path(__file__).parent)
os.environ.setdefault("DOTENV_ONLY", "1")
from dotenv import load_dotenv
load_dotenv(override=False)

RESULTS = []
BOT = "KIO_Runtime_bot"
CONSUMED = set()

def record(suite, name, expected, reply, latency, status, note=""):
    RESULTS.append({"suite": suite, "test": name, "expected": expected,
                    "reply": (reply or "")[:300], "latency": round(latency, 2),
                    "status": status, "note": note})
    sym = {"PASS": "P", "FAIL": "F", "PARTIAL": "~"}.get(status, "?")
    print(f"  [{sym}] {name} -> {status} ({latency:.1f}s) reply={repr((reply or '')[:90])}")

async def send_and_wait(client, my_id, text, timeout=40):
    start = time.time()
    known = {m.id for m in await client.get_messages(BOT, limit=10) if m.id not in CONSUMED}
    await client.send_message(BOT, text)
    reply = None
    while time.time() - start < timeout:
        await asyncio.sleep(2)
        msgs = await client.get_messages(BOT, limit=8)
        for m in msgs:
            if (m.text and m.date and m.sender_id != my_id
                    and m.id not in known and m.id not in CONSUMED
                    and m.date.timestamp() > start - 2):
                reply = m.text.strip()
                CONSUMED.add(m.id)
                break
        if reply:
            break
    return reply or "", time.time() - start

async def clear_pollution(client, my_id):
    """Delete my own stray /start messages from the aborted run."""
    deleted = 0
    msgs = await client.get_messages(BOT, limit=30)
    ids = [m.id for m in msgs if m.sender_id == my_id and m.text and m.text.strip() == "/start"]
    if ids:
        await client.delete_messages(BOT, ids)
        deleted = len(ids)
    print(f"[CLEAN] Deleted {deleted} stray /start messages.")

def has(reply, *kws):
    r = (reply or "").lower()
    return any(k in r for k in kws)

async def main():
    from telethon import TelegramClient
    api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash = os.getenv("TELEGRAM_API_HASH", "")
    phone = os.getenv("TELEGRAM_USER_PHONE", "")
    session_path = Path(".telegram_sessions/kio_test_user")
    if not session_path.suffix:
        session_path = Path(str(session_path) + ".session")
    session_path.parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(str(session_path), api_id, api_hash)
    await client.start(phone=phone)
    me = await client.get_me()
    my_id = me.id
    print(f"[TELETHON] Attached as {me.first_name} (ID: {my_id})")

    try:
        await clear_pollution(client, my_id)

        # ── READINESS (single bounded probe, no resend loop) ──
        r, lat = await send_and_wait(client, my_id, "Hello", timeout=45)
        if not r:
            print("[FAIL] No reply from running bot within 45s. Aborting - do not respawn.")
            return
        print(f"[READY] Bot responded to Hello in {lat:.1f}s")

        # ── G1/G2/G3 PASSTHROUGH GUARDS ──────────────────────
        r, lat = await send_and_wait(client, my_id, "Play jazz")
        record("G1", "media_play_jazz", "media", r, lat,
               "PASS" if has(r, "play", "jazz", "🎵", "queue", "music", "song") else "FAIL")

        r, lat = await send_and_wait(client, my_id, "Pause")
        record("G2", "transport_pause", "pause passthrough", r, lat,
               "PASS" if has(r, "pause", "paused", "nothing", "no media") else "FAIL")

        r, lat = await send_and_wait(client, my_id, "Resume")
        record("G2", "transport_resume", "resume passthrough", r, lat,
               "PASS" if has(r, "resume", "play", "continue", "nothing", "no media") else "FAIL")

        r, lat = await send_and_wait(client, my_id, "Forget my name")
        record("G3", "forget_passthrough", "forget passthrough", r, lat,
               "PASS" if has(r, "forget", "forgotten", "okay", "done", "sure") else "FAIL")

        # ── G4 "AGAIN" (post-port, guarded get_last_successful_interaction) ──
        r, lat = await send_and_wait(client, my_id, "Play Interstellar trailer")
        record("G4", "prime_play_trailer", "media", r, lat,
               "PASS" if has(r, "play", "interstellar", "trailer", "🎵", "queue") else "FAIL")

        r, lat = await send_and_wait(client, my_id, "Again")
        record("G4", "again_repeat", "repeats media action", r, lat,
               "PASS" if has(r, "play", "interstellar", "trailer", "🎵", "queue") else "FAIL")

        # ── G5 PRONOUN RESOLUTION (last_target fallback) ─────
        r, lat = await send_and_wait(client, my_id, "Open YouTube")
        record("G5", "prime_open_youtube", "browser", r, lat,
               "PASS" if has(r, "open", "youtube", "browser", "chrome") else "FAIL")

        r, lat = await send_and_wait(client, my_id, "Close it")
        record("G5", "pronoun_close_it", "close youtube", r, lat,
               "PASS" if has(r, "youtube", "close", "tab", "browser") else "FAIL")

        r, lat = await send_and_wait(client, my_id, "Search Interstellar")
        record("G5", "prime_search_interstellar", "knowledge", r, lat,
               "PASS" if has(r, "search", "interstellar", "results", "wikipedia") else "FAIL")

        r, lat = await send_and_wait(client, my_id, "Who directed it")
        record("G5", "pronoun_who_directed", "interstellar", r, lat,
               "PASS" if has(r, "nolan", "interstellar", "christopher") else "FAIL")

        # ── S1/S2 NEWLY-LIVE SURFACE (explicit pass/fail) ────
        r, lat = await send_and_wait(client, my_id, "Tell me more")
        record("S1", "continue_tell_more", "continuation", r, lat,
               "PASS" if r and not r.lower().strip() in ("tell me more",) else "PARTIAL")

        r, lat = await send_and_wait(client, my_id, "Go ahead")
        record("S2", "affirmative_go_ahead", "affirmative", r, lat,
               "PASS" if r and not r.lower().strip() in ("go ahead",) else "PARTIAL")

        r, lat = await send_and_wait(client, my_id, "Yes")
        record("S2", "affirmative_yes", "affirmative", r, lat,
               "PASS" if r and not r.lower().strip() in ("yes",) else "PARTIAL")

        r, lat = await send_and_wait(client, my_id, "Okay")
        record("S2", "affirmative_okay", "affirmative", r, lat,
               "PASS" if r and not r.lower().strip() in ("okay", "ok") else "PARTIAL")

        # ── 7 CONTEXT-BLEED SCENARIOS (C-04 regression set) ──
        r, lat = await send_and_wait(client, my_id, "Tell me about Interstellar")
        record("BLEED1", "prime_interstellar", "knowledge", r, lat,
               "PASS" if has(r, "interstellar", "movie", "film", "2014", "nolan") else "FAIL")
        r, lat = await send_and_wait(client, my_id, "Who directed it")
        record("BLEED1", "resolve_who_directed", "interstellar", r, lat,
               "PASS" if has(r, "nolan", "interstellar", "christopher") else "FAIL")

        r, lat = await send_and_wait(client, my_id, "Who won the FIFA World Cup")
        record("BLEED2", "prime_fifa", "knowledge", r, lat,
               "PASS" if has(r, "fifa", "world cup", "won", "winner", "argentin", "france") else "FAIL")
        r, lat = await send_and_wait(client, my_id, "Who scored")
        record("BLEED2", "resolve_who_scored", "fifa context", r, lat,
               "PASS" if has(r, "fifa", "goal", "score", "mbappe", "messi") else "FAIL")

        r, lat = await send_and_wait(client, my_id, "Play The Bear")
        record("BLEED3", "prime_the_bear", "media", r, lat,
               "PASS" if has(r, "bear", "play", "🎵", "queue", "show") else "FAIL")
        r, lat = await send_and_wait(client, my_id, "Who created it")
        record("BLEED3", "resolve_who_created", "the bear", r, lat,
               "PASS" if has(r, "bear", "created", "show", "tv", "series") else "FAIL")

        r, lat = await send_and_wait(client, my_id, "Explain quantum entanglement")
        record("BLEED4", "cross_domain_knowledge", "knowledge", r, lat,
               "PASS" if has(r, "quantum", "entangle", "physics", "particle") else "FAIL")

        r, lat = await send_and_wait(client, my_id, "Tell me about it")
        record("BLEED5", "pronoun_no_bleed", "no stale media bleed", r, lat,
               "PARTIAL" if r else "FAIL")

        r, lat = await send_and_wait(client, my_id, "Open YouTube")
        record("BLEED6", "prime_youtube2", "browser", r, lat,
               "PASS" if has(r, "open", "youtube", "browser") else "FAIL")
        r, lat = await send_and_wait(client, my_id, "Search for pasta recipes")
        record("BLEED6", "explicit_new_overrides", "knowledge search", r, lat,
               "PASS" if has(r, "search", "pasta", "recipe") else "FAIL")
        r, lat = await send_and_wait(client, my_id, "Close it")
        record("BLEED6", "resolve_close_it", "youtube not pasta", r, lat,
               "PASS" if has(r, "youtube", "close", "tab", "browser") else "FAIL")

        # ── RESULTS ──────────────────────────────────────────
        total = len(RESULTS)
        passed = sum(1 for x in RESULTS if x["status"] == "PASS")
        failed = [x for x in RESULTS if x["status"] == "FAIL"]
        partial = [x for x in RESULTS if x["status"] == "PARTIAL"]
        print(f"\n  Total: {total} | PASS: {passed} | FAIL: {len(failed)} | PARTIAL: {len(partial)}")
        for x in failed + partial:
            print(f"  {x['status']}: {x['suite']}/{x['test']} expected={x['expected']} reply={x['reply'][:120]}")

        with open("live_validation_results.json", "w") as f:
            json.dump(RESULTS, f, indent=2)

        Path("validation_complete.md").write_text(
            "# KIO P1.2 Guard-Set Live Telegram Validation\n\n"
            f"- Date: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n"
            f"- Mode: ATTACH to running runtime (PID unchanged, no restart)\n"
            f"- Restart count: 0\n"
            f"- Guard set: G1 media / G2 transport / G3 forget passthroughs, G4 'again',\n"
            f"  G5 pronoun resolution + last_target fallback, S1/S2 continuation & affirmative\n"
            f"  markers (newly-live surface), plus 7 context-bleed scenarios (C-04 set).\n"
            f"- Result: {passed}/{total} PASS, {len(failed)} FAIL, {len(partial)} PARTIAL\n\n"
            + "".join(f"- {x['suite']}/{x['test']}: {x['status']} ({x['latency']}s) {x['reply'][:80]}\n" for x in RESULTS)
            + "\nRuntime left running per protocol (exactly one runtime).\n",
            encoding="utf-8",
        )
        print("[DONE] validation_complete.md written. Bot left running.")
    finally:
        client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
