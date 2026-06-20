"""
Discord transport integration tests.

These tests verify that:
1. route() accepts channel="discord" parameter
2. Discord transport can be imported and instantiated
3. Conversation flows 1-5 work through route() 
4. Backward compatibility with Telegram is preserved
"""

import sys
import os
import logging
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")


# ── Test: route() accepts channel param ────────────────────────────

def test_route_accepts_channel_param():
    """route() must accept channel parameter without breaking Telegram calls."""
    from mini_kio.core.command_router import route
    import inspect
    
    sig = inspect.signature(route)
    params = list(sig.parameters.keys())
    assert "channel" in params, f"channel param not found in route(): {params}"
    assert params == ["text", "user_id", "channel"], f"Unexpected param order: {params}"
    print(f"  [OK] route() signature: {sig}")


def test_route_channel_default_is_telegram():
    """route() channel default must be 'telegram' for backward compatibility."""
    from mini_kio.core.command_router import route
    import inspect
    
    sig = inspect.signature(route)
    default = sig.parameters["channel"].default
    assert default == "telegram", f"Default channel should be 'telegram', got {default!r}"
    print(f"  [OK] route() channel default is 'telegram'")


# ── Test: Discord transport module loads cleanly ───────────────────

def test_discord_transport_import():
    """Discord transport module must import without errors."""
    from mini_kio.platform.discord_transport import (
        run_discord,
        start_discord_thread,
        stop_discord_thread,
        _handle_discord_message,
    )
    assert callable(run_discord)
    assert callable(start_discord_thread)
    assert callable(stop_discord_thread)
    assert callable(_handle_discord_message)
    print("  [OK] discord_transport imports cleanly")


def test_discord_transport_start_without_token():
    """start_discord_thread must return False when no token configured."""
    from mini_kio.platform.discord_transport import start_discord_thread
    
    # Temporarily clear token
    import mini_kio.core.config as cfg
    original = cfg.DISCORD_BOT_TOKEN
    try:
        cfg.DISCORD_BOT_TOKEN = ""
        result = start_discord_thread()
        assert result is False, f"Expected False, got {result}"
        print("  [OK] start_discord_thread() returns False without token")
    finally:
        cfg.DISCORD_BOT_TOKEN = original


# ── Test: route() works with channel="discord" ─────────────────────

def test_route_discord_channel_greeting():
    """route() with channel='discord' must return greeting message."""
    from mini_kio.core.command_router import route
    
    resp = route("hello", user_id=12345, channel="discord")
    assert resp is not None
    assert isinstance(resp, str)
    assert len(resp) > 0
    print(f"  [OK] route('hello', channel='discord') -> {resp[:60]}")


def test_route_discord_channel_media_query():
    """route() with channel='discord' must handle media queries."""
    from mini_kio.core.command_router import route
    
    resp = route("Interstellar", user_id=12345, channel="discord")
    assert resp is not None
    assert isinstance(resp, str)
    assert len(resp) > 10
    print(f"  [OK] route('Interstellar', channel='discord') -> {resp[:80]}...")


def test_route_telegram_compat():
    """route() without channel param must still work for Telegram."""
    from mini_kio.core.command_router import route
    
    resp = route("hello", user_id=0)
    assert resp is not None
    assert isinstance(resp, str)
    print(f"  [OK] route('hello') [Telegram compat] -> {resp[:60]}")


# ── Test: Conversation flows through route() ───────────────────────

def test_conversation_1_interstellar():
    """Conversation 1: Interstellar → Who directed it? → Any interviews? → Show them → Play the first one"""
    from mini_kio.core.command_router import route
    
    user_id = 10001
    channel = "discord"
    
    # Step 1: Initial query
    r1 = route("Interstellar", user_id=user_id, channel=channel)
    assert r1 and len(r1) > 10, f"Initial query failed: {r1}"
    print(f"  [1] Interstellar -> {r1[:80]}...")
    
    # Step 2: Follow-up question (tests media continuity)
    r2 = route("Who directed it?", user_id=user_id, channel=channel)
    assert r2 and len(r2) > 5, f"Follow-up failed: {r2}"
    print(f"  [2] Who directed it? -> {r2[:80]}...")
    
    # Step 3: Artifact request
    r3 = route("Any interviews?", user_id=user_id, channel=channel)
    assert r3 and len(r3) > 5, f"Artifact request failed: {r3}"
    print(f"  [3] Any interviews? -> {r3[:80]}...")
    
    # Step 4: Show them
    r4 = route("Show them", user_id=user_id, channel=channel)
    assert r4 is not None, f"Show them failed: {r4}"
    print(f"  [4] Show them -> {r4[:80]}...")
    
    # Step 5: Play the first one
    r5 = route("Play the first one", user_id=user_id, channel=channel)
    assert r5 is not None, f"Play first one failed: {r5}"
    print(f"  [5] Play the first one -> {r5[:80]}...")
    
    print("  [OK] Conversation 1 complete")


def test_conversation_2_the_bear():
    """Conversation 2: The Bear → Show trailer"""
    from mini_kio.core.command_router import route
    
    user_id = 10002
    channel = "discord"
    
    r1 = route("The Bear", user_id=user_id, channel=channel)
    assert r1 and len(r1) > 5, f"Initial query failed: {r1}"
    print(f"  [1] The Bear -> {r1[:80]}...")
    
    r2 = route("Show trailer", user_id=user_id, channel=channel)
    assert r2 is not None, f"Show trailer failed: {r2}"
    print(f"  [2] Show trailer -> {r2[:80]}...")
    
    print("  [OK] Conversation 2 complete")


def test_conversation_3_fifa():
    """Conversation 3: Latest FIFA World Cup updates → Show highlights"""
    from mini_kio.core.command_router import route
    
    user_id = 10003
    channel = "discord"
    
    r1 = route("Latest FIFA World Cup updates", user_id=user_id, channel=channel)
    assert r1 and len(r1) > 5, f"Initial query failed: {r1}"
    print(f"  [1] Latest FIFA World Cup updates -> {r1[:80]}...")
    
    r2 = route("Show highlights", user_id=user_id, channel=channel)
    assert r2 is not None, f"Show highlights failed: {r2}"
    print(f"  [2] Show highlights -> {r2[:80]}...")
    
    print("  [OK] Conversation 3 complete")


def test_conversation_4_believer():
    """Conversation 4: Believer → Live version"""
    from mini_kio.core.command_router import route
    
    user_id = 10004
    channel = "discord"
    
    r1 = route("Believer", user_id=user_id, channel=channel)
    assert r1 and len(r1) > 5, f"Initial query failed: {r1}"
    print(f"  [1] Believer -> {r1[:80]}...")
    
    r2 = route("Live version", user_id=user_id, channel=channel)
    assert r2 is not None, f"Live version failed: {r2}"
    print(f"  [2] Live version -> {r2[:80]}...")
    
    print("  [OK] Conversation 4 complete")


def test_conversation_5_open_telegram():
    """Conversation 5: Open Telegram (browser action)"""
    from mini_kio.core.command_router import route
    
    user_id = 10005
    channel = "discord"
    
    r = route("Open Telegram", user_id=user_id, channel=channel)
    assert r is not None
    print(f"  Open Telegram -> {r[:80]}...")
    
    print("  [OK] Conversation 5 complete")


# ── Test: config has Discord vars ──────────────────────────────────

def test_config_has_discord_vars():
    """config.py must export DISCORD_BOT_TOKEN, DISCORD_APPLICATION_ID."""
    from mini_kio.core.config import DISCORD_BOT_TOKEN, DISCORD_APPLICATION_ID, DISCORD_ENABLED
    assert isinstance(DISCORD_BOT_TOKEN, str)
    assert isinstance(DISCORD_APPLICATION_ID, str)
    assert isinstance(DISCORD_ENABLED, bool)
    print(f"  [OK] config: DISCORD_BOT_TOKEN={'set' if DISCORD_BOT_TOKEN else 'empty'} "
          f"DISCORD_ENABLED={DISCORD_ENABLED}")


if __name__ == "__main__":
    tests = [fn for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    passed = 0
    failed = 0
    
    for fn in tests:
        test_name = fn.__name__
        print(f"\n=== {test_name} ===")
        try:
            fn()
            print("  PASS")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  FAIL: {e}")
            traceback.print_exc()
            failed += 1
    
    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if failed:
        sys.exit(1)
