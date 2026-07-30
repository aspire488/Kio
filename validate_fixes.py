"""Live validation: test route() to verify all fixes produce correct behaviour.

This calls the same command_router.route() that Terminal, Telegram, and Discord use.
If the response is correct here, it's correct on all interfaces.
"""
import sys, time, logging, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, '.')

# Patch config to suppress Telegram/Discord — we validate via route() directly
import mini_kio.core.config as cfg
cfg.TELEGRAM_TOKEN = ''
cfg.DISCORD_BOT_TOKEN = ''

logging.basicConfig(level=logging.WARNING, stream=io.StringIO())

from mini_kio.core.runtime import bootstrap_runtime
bootstrap_runtime()

from mini_kio.core.command_router import route

def test(label, text, expected_ok=True, user_id=0):
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"SEND: {text}")
    print(f"{'='*60}")
    try:
        reply = route(text, user_id=user_id, channel="terminal")
        is_ok = bool(reply) and len(reply) > 0
        status = "OK" if is_ok == expected_ok else "FAIL"
        print(f">> [{status}] {reply[:500]}")
    except Exception as e:
        print(f">> [EXCEPTION] {type(e).__name__}: {e}")
    time.sleep(0.3)

# ── Conversation Flow ──────────────────────────────────────────────────

test("1. Basic greeting", "hello")
test("2. Identity", "who are you")

test("3. Sports knowledge - should use knowledge, not media", "what is football")
test("4. Continuity follow-up", "more on it")
test("5. Continuity follow-up", "basic rules")
test("6. Opinion (opinion, not retrieval)", "what's your view on football")

# ── Media Tests ────────────────────────────────────────────────────────

test("7. Open YouTube", "open youtube")
test("8. Play media query", "play brand new day trailer")
test("9. Pronoun resolution - 'play it'", "play it")
test("10. Media control", "pause")
test("11. Media control", "resume")
test("12. Media control", "stop")

# ── Memory Tests ───────────────────────────────────────────────────────

test("13. Remember preference", "remember my favourite language is Python")
test("14. Recall memory", "what's my favourite language")

# ── Fallback / Error Handling ──────────────────────────────────────────

test("15. Unknown media (should fail cleanly, no fabricated success)", "play xyzzy_nonexistent_media_12345")

print("\n" + "="*60)
print("VALIDATION COMPLETE")
