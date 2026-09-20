"""Phase 1 — Bounded live acceptance matrix (A–H)."""
import asyncio, os, sys, time, glob, random, string

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()
API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
SESSION = ".telegram_sessions/kio_test_user.session"
TARGET = "KIO_Runtime_bot"
TIMEOUT = 45  # seconds per test

# ── Fresh test inputs (never reused) ───────────────────────────
TOPICS = [
    "the discovery of penicillin",
    "how photosynthesis converts light to energy",
    "the fall of the Berlin Wall",
    "CRISPR gene editing mechanisms",
    "the James Webb Space Telescope discoveries",
    "plate tectonics and earthquake formation",
    "the history of cryptography",
    "how black holes form",
    "the economic impact of the semiconductor shortage",
    "the Voyager 1 mission status",
]
random.seed()
TOPIC = random.choice(TOPICS)
SUBJECTS = [
    "the invention of the printing press",
    "how neural networks learn",
    "the Voyager golden record",
    "the chemistry of coffee brewing",
    "why the sky is blue",
    "the engineering behind suspension bridges",
]
SUBJECT = random.choice(SUBJECTS)
DOC_SUBJECT = random.choice(["quantum computing applications in healthcare", "the history of the Silk Road", "renewable energy adoption trends"])


async def run_tests():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (ID: {me.id})")

    results = {}

    # ── Helper: send text, wait for reply ──────────────────────
    async def send_text(label, text, expect_voice=False):
        print(f"\n{'='*60}")
        print(f"TEST {label}: {text!r}")
        print(f"{'='*60}")
        t0 = time.monotonic()
        sent = await client.send_message(TARGET, text)
        got_text = False
        got_voice = False
        reply_text = ""
        reply_voice_bytes = 0
        stage = "sent"

        while time.monotonic() - t0 < TIMEOUT:
            await asyncio.sleep(2)
            msgs = await client.get_messages(TARGET, limit=5)
            for msg in msgs:
                if msg.date and msg.date.timestamp() > t0 - 2 and msg.id > sent.id:
                    elapsed = time.monotonic() - t0
                    if msg.text and not got_text:
                        got_text = True
                        reply_text = msg.text
                        stage = "text_received"
                        print(f"  [{elapsed:.1f}s] TEXT ({len(msg.text)} chars): {msg.text[:200]!r}")
                    if msg.voice and not got_voice:
                        got_voice = True
                        reply_voice_bytes = msg.voice.size
                        stage = "voice_received"
                        print(f"  [{elapsed:.1f}s] VOICE: {msg.voice.size} bytes")
                    if got_text and (not expect_voice or got_voice):
                        break
            if got_text and (not expect_voice or got_voice):
                break

        elapsed = time.monotonic() - t0
        # Check for .docx files created in last 60s
        recent_docs = [f for f in glob.glob("*.docx") if os.path.getmtime(f) > t0 - 5]

        r = {
            "label": label,
            "input": text,
            "got_text": got_text,
            "got_voice": got_voice,
            "reply_text": reply_text[:500],
            "reply_voice_bytes": reply_voice_bytes,
            "docx_created": bool(recent_docs),
            "docx_files": recent_docs,
            "elapsed_s": round(elapsed, 1),
            "stage": stage,
        }
        results[label] = r
        print(f"  RESULT: text={got_text} voice={got_voice} docx={bool(recent_docs)} elapsed={elapsed:.1f}s stage={stage}")
        return r

    # ── Helper: send voice note ────────────────────────────────
    async def send_voice(label, text, expect_voice=True):
        print(f"\n{'='*60}")
        print(f"TEST {label} (VOICE INPUT): {text!r}")
        print(f"{'='*60}")
        t0 = time.monotonic()

        # Generate voice note via edge-tts
        voice_file = f"_test_{label}.ogg"
        try:
            import edge_tts, subprocess
            tts = edge_tts.Communicate(text, "en-US-GuyNeural", rate="+0%")
            mp3_path = f"_test_{label}.mp3"
            await tts.save(mp3_path)
            subprocess.run([
                "ffmpeg", "-y", "-i", mp3_path, "-c:a", "libopus", "-b:a", "32k", voice_file,
            ], capture_output=True, timeout=15)
            os.remove(mp3_path)
            if not os.path.exists(voice_file):
                print(f"  SKIP: could not generate voice note")
                results[label] = {"label": label, "stage": "voice_gen_failed"}
                return results[label]
        except Exception as e:
            print(f"  SKIP: voice generation error: {e}")
            results[label] = {"label": label, "stage": "voice_gen_error", "error": str(e)}
            return results[label]

        size = os.path.getsize(voice_file)
        print(f"  Sending voice note ({size} bytes)...")
        sent = await client.send_file(TARGET, voice_file, voice_notes=True)
        got_text = False
        got_voice = False
        reply_text = ""
        reply_voice_bytes = 0
        stage = "voice_sent"

        while time.monotonic() - t0 < TIMEOUT + 15:
            await asyncio.sleep(2)
            msgs = await client.get_messages(TARGET, limit=5)
            for msg in msgs:
                if msg.date and msg.date.timestamp() > t0 - 2 and msg.id > sent.id:
                    elapsed = time.monotonic() - t0
                    if msg.text and not got_text:
                        got_text = True
                        reply_text = msg.text
                        stage = "text_received"
                        print(f"  [{elapsed:.1f}s] TEXT ({len(msg.text)} chars): {msg.text[:200]!r}")
                    if msg.voice and not got_voice:
                        got_voice = True
                        reply_voice_bytes = msg.voice.size
                        stage = "voice_received"
                        print(f"  [{elapsed:.1f}s] VOICE: {msg.voice.size} bytes")
                    if got_text and (not expect_voice or got_voice):
                        break
            if got_text and (not expect_voice or got_voice):
                break

        elapsed = time.monotonic() - t0
        recent_docs = [f for f in glob.glob("*.docx") if os.path.getmtime(f) > t0 - 5]

        if os.path.exists(voice_file):
            os.remove(voice_file)

        r = {
            "label": label,
            "input": f"[voice note: {text!r}]",
            "got_text": got_text,
            "got_voice": got_voice,
            "reply_text": reply_text[:500],
            "reply_voice_bytes": reply_voice_bytes,
            "docx_created": bool(recent_docs),
            "docx_files": recent_docs,
            "elapsed_s": round(elapsed, 1),
            "stage": stage,
        }
        results[label] = r
        print(f"  RESULT: text={got_text} voice={got_voice} docx={bool(recent_docs)} elapsed={elapsed:.1f}s stage={stage}")
        return r

    # ── A: Fresh typed informational query ─────────────────────
    await send_text("A", f"Explain how {TOPIC} works")

    # ── B: Fresh current/latest query (freshness required) ─────
    await send_text("B", f"What is the latest news about {SUBJECT}?")

    # ── C: Fresh typed voice request ───────────────────────────
    await send_text("C", f"Give me a voice reply about {SUBJECT}", expect_voice=True)

    # ── D: Fresh voice-note question ───────────────────────────
    await send_voice("D", f"What are the main causes of climate change")

    # ── E: Voice-note that could look like artifact request ────
    await send_voice("E", f"Write me a summary about {SUBJECT}")

    # ── F: Explicit document request ───────────────────────────
    await send_text("F", f"Create a report about {DOC_SUBJECT}")

    # ── G: Referential voice (first get an answer, then ask to speak it)
    print(f"\n{'='*60}")
    print(f"TEST G (two-step referential)")
    print(f"{'='*60}")
    t0g = time.monotonic()
    g1 = await client.send_message(TARGET, f"What is {SUBJECT}?")
    await asyncio.sleep(1)
    g1_reply = ""
    while time.monotonic() - t0g < TIMEOUT:
        await asyncio.sleep(2)
        msgs = await client.get_messages(TARGET, limit=3)
        for msg in msgs:
            if msg.date and msg.date.timestamp() > t0g - 2 and msg.id > g1.id and msg.text:
                g1_reply = msg.text
                print(f"  G1 TEXT: {g1_reply[:200]!r}")
                break
        if g1_reply:
            break

    if g1_reply:
        # Now ask to speak it
        t0g2 = time.monotonic()
        g2 = await client.send_message(TARGET, "Say that out loud")
        got_voice_g = False
        while time.monotonic() - t0g2 < TIMEOUT:
            await asyncio.sleep(2)
            msgs = await client.get_messages(TARGET, limit=3)
            for msg in msgs:
                if msg.date and msg.date.timestamp() > t0g2 - 2 and msg.id > g2.id and msg.voice:
                    got_voice_g = True
                    print(f"  G2 VOICE: {msg.voice.size} bytes")
                    break
            if got_voice_g:
                break
        results["G"] = {"label": "G", "step1_text": bool(g1_reply), "step2_voice": got_voice_g, "elapsed_s": round(time.monotonic() - t0g, 1)}
    else:
        results["G"] = {"label": "G", "step1_text": False, "stage": "step1_failed"}

    # ── H: Fresh long-form voice request ───────────────────────
    await send_voice("H", f"Explain in detail the history and significance of {DOC_SUBJECT} and why it matters today")

    # ── Summary ────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("ACCEPTANCE MATRIX RESULTS")
    print(f"{'='*60}")
    for label in ["A", "B", "C", "D", "E", "F", "G", "H"]:
        r = results.get(label, {})
        text_ok = "PASS" if r.get("got_text") else "FAIL"
        voice_ok = "PASS" if r.get("got_voice") else ("N/A" if label in ("A", "B", "F") else "FAIL")
        docx_ok = "PASS" if not r.get("docx_created") else ("PASS" if label == "F" else "FAIL")
        elapsed = r.get("elapsed_s", "?")
        print(f"  {label}: text={text_ok} voice={voice_ok} docx={docx_ok} elapsed={elapsed}s")
        if r.get("reply_text"):
            print(f"       reply: {r['reply_text'][:150]!r}")

    await client.disconnect()
    return results


if __name__ == "__main__":
    asyncio.run(run_tests())
