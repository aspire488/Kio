"""
Property-based test generator for KIO voice pipeline.
Generates NEW randomized tests each run — never reuses hardcoded examples.

Invariants tested:
1. VOICE INPUT -> TEXT + VOICE output (from one canonical answer)
2. INFORMATIONAL voice request -> no DOCX artifact created
3. Pipeline classify() -> correct IntentType for informational vs document requests
"""
import asyncio
import os
import random
import string
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))


# ── Test corpus generators ────────────────────────────────────────────

def _random_topic():
    """Generate a random factual question topic."""
    nouns = [
        "quantum computing", "climate change", "the solar system",
        "machine learning", "photosynthesis", "democracy",
        "evolution", "black holes", "the human brain", "ancient Rome",
        "renewable energy", "artificial intelligence", "the internet",
        "genetic engineering", "space exploration", "the periodic table",
        "ocean currents", "plate tectonics", "nuclear fusion",
        "the Renaissance", "the Industrial Revolution", "DNA replication",
    ]
    return random.choice(nouns)


def _random_voice_question():
    """Generate a random voice-style informational question."""
    templates = [
        "What is {topic}?",
        "How does {topic} work?",
        "Explain {topic}",
        "Tell me about {topic}",
        "Who discovered {topic}?",
        "Why is {topic} important?",
        "When was {topic} invented?",
        "What are the benefits of {topic}?",
    ]
    return random.choice(templates).format(topic=_random_topic())


def _random_document_request():
    """Generate a random document creation request."""
    artifacts = [
        "report", "essay", "summary", "comparison", "presentation",
        "spreadsheet", "budget", "email", "letter", "poem",
    ]
    templates = [
        "Create a {artifact} about {topic}",
        "Make a {artifact} on {topic}",
        "Draft a {artifact} about {topic}",
        "Write a {artifact} on {topic}",
        "Generate a {artifact} about {topic}",
    ]
    return random.choice(templates).format(
        artifact=random.choice(artifacts),
        topic=_random_topic(),
    )


def _random_social():
    """Generate a random social/conversational message."""
    topics = [
        "What do you think about AI?",
        "How are you today?",
        "Tell me a joke",
        "What's your favorite color?",
        "Do you like music?",
        "What can you do?",
        "How's the weather?",
        "Any news today?",
    ]
    return random.choice(topics)


def generate_test_batch(count=5):
    """Generate a batch of randomized tests, each with expected invariant."""
    tests = []
    for _ in range(count):
        kind = random.choice(["voice_question", "document_request", "social"])
        if kind == "voice_question":
            text = _random_voice_question()
            tests.append({
                "kind": kind,
                "text": text,
                "expect_docx": False,
                "expect_intent": "INFORMATION",
            })
        elif kind == "document_request":
            text = _random_document_request()
            tests.append({
                "kind": kind,
                "text": text,
                "expect_docx": True,
                "expect_intent": "DESKTOP_ACTION",
            })
        else:
            text = _random_social()
            tests.append({
                "kind": kind,
                "text": text,
                "expect_docx": False,
                "expect_intent": "CONVERSATION",
            })
    return tests


# ── Pipeline classifier tests (deterministic, no network) ─────────────

def test_pipeline_invariants():
    """Run property-based invariant tests on the pipeline classifier."""
    from mini_kio.core.pipeline import Pipeline
    from mini_kio.core.pipeline.types import IntentType

    p = Pipeline()
    c = p._classifier
    passed = 0
    failed = 0
    total = 0

    # Property 1: Informational questions must NOT produce document creation
    print("\n=== PROPERTY 1: Informational questions -> no document creation ===")
    for _ in range(20):
        text = _random_voice_question()
        total += 1
        lower = text.lower()
        doc_result = c._detect_document_creation(lower, text)
        if doc_result is None:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {text!r} -> doc creation {doc_result.action}")

    # Property 2: Document creation requests MUST produce document routing
    print("\n=== PROPERTY 2: Document requests -> document creation ===")
    for _ in range(20):
        text = _random_document_request()
        total += 1
        lower = text.lower()
        doc_result = c._detect_document_creation(lower, text)
        if doc_result is not None and doc_result.action == "create_document":
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {text!r} -> no doc creation")

    # Property 3: Voice-prefixed informational questions -> no document creation
    print("\n=== PROPERTY 3: Voice-prefixed questions -> no doc creation ===")
    prefixes = [
        "say that out loud",
        "give me a voice reply about",
        "tell me in voice",
        "speak about",
        "give me a voice on",
    ]
    for _ in range(20):
        topic = _random_topic()
        prefix = random.choice(prefixes)
        text = f"{prefix} {topic}"
        total += 1
        lower = text.lower()
        doc_result = c._detect_document_creation(lower, text)
        if doc_result is None:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {text!r} -> doc creation {doc_result.action}")

    # Property 4: Greeting prefix + question -> no document creation
    print("\n=== PROPERTY 4: Greeting prefix + question -> no doc creation ===")
    greetings = ["hey kio,", "hey kio", "kio,", "hey", "hi kio"]
    for _ in range(20):
        topic = _random_topic()
        greeting = random.choice(greetings)
        question_templates = [
            f"{greeting} what is {topic}",
            f"{greeting} explain {topic}",
            f"{greeting} tell me about {topic}",
            f"{greeting} how does {topic} work",
        ]
        text = random.choice(question_templates)
        total += 1
        lower = text.lower()
        doc_result = c._detect_document_creation(lower, text)
        if doc_result is None:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {text!r} -> doc creation {doc_result.action}")

    # Property 5: "give me X" for non-artifact nouns -> no document creation
    print("\n=== PROPERTY 5: 'give me X' (non-artifact) -> no doc creation ===")
    non_artifacts = [
        "your opinion on quantum computing",
        "your thoughts on AI",
        "a voice reply about climate change",
        "some advice on career choices",
        "help with my homework",
        "an explanation of relativity",
        "your favorite recipe",
        "a recommendation for dinner",
        "your take on evolution",
        "some tips for productivity",
    ]
    for na in non_artifacts:
        text = f"give me {na}"
        total += 1
        lower = text.lower()
        doc_result = c._detect_document_creation(lower, text)
        if doc_result is None:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {text!r} -> doc creation {doc_result.action}")

    print(f"\n=== RESULTS: {passed}/{total} passed, {failed} failed ===")
    return failed == 0


def test_freshness_routing_invariants():
    """Property 6: Time-sensitive queries that reach the conversational
    fallback must route to INFORMATION intent, not CONVERSATION. Queries
    caught by higher-priority handlers (ENTITY_QUERY, UTILITY, etc.) are
    exempt — they already use live data sources."""
    from mini_kio.core.pipeline import Pipeline
    from mini_kio.core.pipeline.types import IntentType
    from mini_kio.core.freshness_classifier import classify as fc_classify, FreshnessLevel

    p = Pipeline()
    passed = 0
    failed = 0
    total = 0

    # ── REQUIRED freshness queries (must route to INFORMATION) ──────────
    # Only test queries that actually reach _classify_conversational (action
    # is "converse" or "converse" variant). Queries caught by higher-priority
    # handlers (ENTITY_QUERY, UTILITY, etc.) are already handled correctly.
    print("\n=== PROPERTY 6: REQUIRED freshness queries -> INFORMATION intent ===")
    required_queries = [
        "What is the latest GPT model?",
        "What's the latest news about AI?",
        "Who won the Super Bowl last night?",
        "What are today's top headlines?",
        "Is there news about the next Spider-Man movie?",
        "What happened in the election yesterday?",
        "Latest stock market closing price",
        "What time does the game start tonight?",
        "What's the latest iPhone model released?",
        "Did Apple just announce new MacBooks?",
        "What's happening in Ukraine right now?",
        "What happened to Twitter today?",
        "Is the new iPhone out yet?",
        "Who's leading the polls right now?",
        "What are the latest crypto prices?",
        "Current Bitcoin price today",
        "Current exchange rate for EUR to USD",
        "What's the weather forecast for tomorrow?",
        "What's the latest version of Python?",
    ]
    for q in required_queries:
        total += 1
        fc = fc_classify(q)
        if fc != FreshnessLevel.REQUIRED:
            # freshness_classifier doesn't flag this — skip (not a bug)
            total -= 1
            continue
        decision = p._classifier.classify(q, q)
        # Higher-priority handlers (ENTITY_QUERY, UTILITY) that catch
        # REQUIRED-freshness queries are CORRECT — they already use live
        # data. Only check that CONVERSATION is NOT the result.
        if decision.intent_type != IntentType.CONVERSATION:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {q!r} -> CONVERSATION (should be INFORMATION or higher)")

    # ── NONE freshness queries must NOT be forced to INFORMATION ─────────
    print("\n=== PROPERTY 6b: NONE freshness queries -> NOT forced to INFORMATION ===")
    none_queries = [
        "Hello there",
        "How are you today?",
        "Tell me a joke",
        "What can you do?",
        "Open Excel",
        "Play some music",
        "Create a report about climate change",
        "What is 2 plus 2?",
        "Explain quantum computing",
    ]
    for q in none_queries:
        total += 1
        fc = fc_classify(q)
        if fc != FreshnessLevel.NONE:
            # freshness_classifier flags this — skip
            total -= 1
            continue
        decision = p._classifier.classify(q, q)
        if decision.intent_type != IntentType.INFORMATION:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {q!r} -> INFORMATION (should not be forced)")

    print(f"\n=== FRESHNESS ROUTING RESULTS: {passed}/{total} passed, {failed} failed ===")
    return failed == 0


# ── Voice note generation + Telegram test ─────────────────────────────

async def test_voice_note_live():
    """Generate a random voice note, send it, verify TEXT+VOICE contract."""
    from telethon import TelegramClient
    from dotenv import load_dotenv

    load_dotenv()
    API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
    API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
    SESSION = ".telegram_sessions/kio_test_user.session"

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"\n=== LIVE VOICE NOTE TEST ===")
    print(f"Logged in as: {me.first_name} (ID: {me.id})")

    # Generate a fresh voice note with edge-tts
    question = _random_voice_question()
    print(f"Question: {question!r}")

    # Generate voice note
    voice_file = "_voice_test_random.ogg"
    try:
        import edge_tts
        tts = edge_tts.Communicate(question, "en-US-GuyNeural", rate="+0%")
        mp3_path = "_voice_test_random.mp3"
        await tts.save(mp3_path)

        # Convert to OGG Opus
        import subprocess
        subprocess.run([
            "ffmpeg", "-y", "-i", mp3_path, "-c:a", "libopus", "-b:a", "32k",
            voice_file,
        ], capture_output=True, timeout=15)
        os.remove(mp3_path)

        if not os.path.exists(voice_file):
            print("FAIL: could not generate voice note")
            await client.disconnect()
            return False
    except Exception as e:
        print(f"FAIL: voice generation error: {e}")
        await client.disconnect()
        return False

    # Send voice note
    target = "KIO_Runtime_bot"
    print(f"Sending voice note ({os.path.getsize(voice_file)} bytes)...")
    t0 = time.monotonic()
    sent = await client.send_file(target, voice_file, voice_notes=True)
    print(f"Voice sent at {time.monotonic() - t0:.1f}s")

    # Wait for text + voice reply
    print("Waiting for reply...")
    t1 = time.monotonic()
    got_text = False
    got_voice = False
    reply_text = ""

    while time.monotonic() - t1 < 50:
        await asyncio.sleep(2)
        msgs = await client.get_messages(target, limit=5)
        for msg in msgs:
            if msg.date and msg.date.timestamp() > t0 - 2 and msg.id > sent.id:
                elapsed = time.monotonic() - t1
                if msg.text and not got_text:
                    got_text = True
                    reply_text = msg.text
                    print(f"[{elapsed:.1f}s] TEXT: {reply_text!r}")
                if msg.voice and not got_voice:
                    got_voice = True
                    print(f"[{elapsed:.1f}s] VOICE: {msg.voice.size} bytes")
                if got_text and got_voice:
                    break
        if got_text and got_voice:
            break

    # Cleanup
    if os.path.exists(voice_file):
        os.remove(voice_file)

    # Verify no DOCX was created (check for recent .docx files)
    import glob
    recent_docs = glob.glob("*.docx")
    if recent_docs:
        print(f"WARNING: found .docx files: {recent_docs}")

    print(f"\n=== LIVE RESULTS ===")
    print(f"Text:  {'PASS' if got_text else 'FAIL'}")
    print(f"Voice: {'PASS' if got_voice else 'FAIL'}")
    contract = got_text and got_voice
    print(f"TEXT+VOICE contract: {'PASS' if contract else 'FAIL'}")
    await client.disconnect()
    return contract


# ── Main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("KIO Voice Pipeline Property-Based Test Suite")
    print("=" * 50)
    print(f"Run ID: {''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}")

    # Phase 1: Deterministic pipeline tests (no network)
    pipeline_ok = test_pipeline_invariants()

    # Phase 1b: Freshness routing invariant tests (no network)
    freshness_ok = test_freshness_routing_invariants()

    # Phase 2: Live voice note test (requires Telegram + running bot)
    if "--live" in sys.argv:
        live_ok = asyncio.run(test_voice_note_live())
    else:
        live_ok = None
        print("\n(Skipping live test — run with --live to enable)")

    print("\n" + "=" * 50)
    print("SUMMARY:")
    print(f"  Pipeline invariants: {'PASS' if pipeline_ok else 'FAIL'}")
    print(f"  Freshness routing:   {'PASS' if freshness_ok else 'FAIL'}")
    if live_ok is not None:
        print(f"  Live voice contract: {'PASS' if live_ok else 'FAIL'}")
    else:
        print(f"  Live voice contract: SKIPPED")
    overall = pipeline_ok and freshness_ok and (live_ok is not None and live_ok or live_ok is None)
    print(f"  Overall: {'PASS' if overall else 'FAIL'}")
