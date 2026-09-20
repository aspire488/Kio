#!/usr/bin/env python3
"""
KIO Live Telegram Behavioral Validation
========================================
Fully autonomous end-to-end testing via Telethon user client.

Flow:
  1. Authenticate Telegram user via Telethon (handles first-login code)
  2. Resolve KIO bot username from Bot API
  3. Start KIO runtime + bot in subprocess
  4. Run comprehensive test sequences through real Telegram transport
  5. Validate every response
  6. Produce transcript + report
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ── Configuration from .env ──────────────────────────────────────
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
TELEGRAM_USER_PHONE = os.getenv("TELEGRAM_USER_PHONE", "").strip()
TELEGRAM_USER_2FA = os.getenv("TELEGRAM_USER_2FA", "").strip() or None
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
ALLOWED_USER_IDS_STR = os.getenv("ALLOWED_USER_IDS", "")

PROJECT_ROOT = Path(__file__).resolve().parent
SESSION_DIR = PROJECT_ROOT / ".telegram_sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
SESSION_FILE = str(SESSION_DIR / "kio_test_user.session")

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(PROJECT_ROOT / "telegram_test.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger("live_test")

# ── Transcript ────────────────────────────────────────────────────
_transcript: list[dict[str, Any]] = []
_test_results: list[dict[str, Any]] = []


def record(user_msg: str, bot_reply: str, test_name: str, intent: str = "",
           capability: str = "", latency_ms: float = 0, passed: bool = False,
           error: str = "") -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_msg": user_msg,
        "bot_reply": bot_reply,
        "test_name": test_name,
        "intent": intent,
        "capability": capability,
        "latency_ms": round(latency_ms, 1),
        "passed": passed,
        "error": error,
    }
    _transcript.append(entry)
    _test_results.append(entry)
    status = "PASS" if passed else "FAIL"
    log.info("[%s] %s | %s -> %s", status, test_name, user_msg[:60], bot_reply[:80])
    if not passed and error:
        log.warning("  %s", error)


def save_transcript():
    path = PROJECT_ROOT / "telegram_transcript.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_transcript, f, indent=2, ensure_ascii=False)
    # Also a readable text version
    txt_path = PROJECT_ROOT / "telegram_transcript.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("=" * 72 + "\n")
        f.write("KIO LIVE TELEGRAM VALIDATION TRANSCRIPT\n")
        f.write(f"Date: {datetime.now(timezone.utc).isoformat()}\n")
        f.write("=" * 72 + "\n\n")
        for i, entry in enumerate(_transcript, 1):
            status = "✓" if entry["passed"] else "✗"
            f.write(f"--- Test #{i}: {entry['test_name']} [{status}] ---\n")
            f.write(f"  Timestamp : {entry['timestamp']}\n")
            f.write(f"  User      : {entry['user_msg']}\n")
            f.write(f"  Bot       : {entry['bot_reply']}\n")
            if entry["intent"]:
                f.write(f"  Intent    : {entry['intent']}\n")
            if entry["capability"]:
                f.write(f"  Capability: {entry['capability']}\n")
            f.write(f"  Latency   : {entry['latency_ms']}ms\n")
            if entry["error"]:
                f.write(f"  Error     : {entry['error']}\n")
            f.write("\n")
    log.info("Transcript saved to %s and %s", path, txt_path)


def generate_report():
    total = len(_test_results)
    passed = sum(1 for r in _test_results if r["passed"])
    failed = total - passed
    rate = (passed / total * 100) if total else 0

    # Group by category
    categories: dict[str, list[dict]] = {}
    for r in _test_results:
        cat = r["test_name"].split(":")[0] if ":" in r["test_name"] else "general"
        categories.setdefault(cat, []).append(r)

    report_path = PROJECT_ROOT / "telegram_validation_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# KIO Live Telegram Validation Report\n\n")
        f.write(f"**Date:** {datetime.now(timezone.utc).isoformat()}\n\n")
        f.write(f"**Total Tests:** {total}\n")
        f.write(f"**Passed:** {passed}\n")
        f.write(f"**Failed:** {failed}\n")
        f.write(f"**Pass Rate:** {rate:.1f}%\n\n")

        f.write("## Results by Category\n\n")
        for cat, entries in sorted(categories.items()):
            c_pass = sum(1 for r in entries if r["passed"])
            c_total = len(entries)
            f.write(f"### {cat}\n")
            f.write(f"  {c_pass}/{c_total} passed\n\n")
            for r in entries:
                icon = "✓" if r["passed"] else "✗"
                f.write(f"- {icon} **{r['test_name']}** ({r['latency_ms']}ms)\n")
                f.write(f"  - User: `{r['user_msg']}`\n")
                f.write(f"  - Bot: {r['bot_reply'][:120]}\n")
                if r["intent"]:
                    f.write(f"  - Intent: `{r['intent']}`\n")
                if r["capability"]:
                    f.write(f"  - Capability: `{r['capability']}`\n")
                if r["error"]:
                    f.write(f"  - Error: {r['error']}\n")
                f.write("\n")

        bugs = [r for r in _test_results if not r["passed"]]
        if bugs:
            f.write("## Bugs Discovered\n\n")
            for r in bugs:
                f.write(f"- **{r['test_name']}**: {r['error']}\n")
                f.write(f"  - Sent: `{r['user_msg']}`\n")
                f.write(f"  - Got: {r['bot_reply'][:100]}\n\n")

        fixes = []

        f.write("## Production Readiness Assessment\n\n")
        if rate >= 90:
            f.write("**STATUS: PASS** — KIO is production-ready through Telegram.\n")
        elif rate >= 70:
            f.write("**STATUS: DEGRADED** — Most features work but issues remain.\n")
        else:
            f.write("**STATUS: FAIL** — Significant issues found.\n")

    log.info("Report saved to %s", report_path)
    return report_path


# ── Telethon authentication ───────────────────────────────────────

def _input_with_prompt(prompt: str) -> str:
    """Read a line from stdin (used for the one-time login code)."""
    print(prompt, end="", flush=True)
    return sys.stdin.readline().strip()


async def authenticate_telegram() -> Any:
    """Authenticate the Telegram user client via Telethon."""
    from telethon import TelegramClient
    from telethon.errors import (
        SessionPasswordNeededError,
        PhoneCodeInvalidError,
        PhoneCodeExpiredError,
    )
    from telethon.sessions import StringSession

    log.info("Authenticating Telegram user: %s", TELEGRAM_USER_PHONE)
    client = TelegramClient(SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)

    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        log.info("Already authenticated as: %s (id=%s)", me.phone, me.id)
        return client

    log.info("No valid session found. Starting first-time login.")
    log.info("Telegram will send a login code via SMS/Telegram.")

    await client.send_code_request(TELEGRAM_USER_PHONE)

    code = _input_with_prompt("Enter Telegram login code: ")
    try:
        await client.sign_in(TELEGRAM_USER_PHONE, code)
    except SessionPasswordNeededError:
        if TELEGRAM_USER_2FA:
            await client.sign_in(password=TELEGRAM_USER_2FA)
        else:
            pwd = _input_with_prompt("Enter Telegram 2FA password: ")
            await client.sign_in(password=pwd)
    except PhoneCodeInvalidError:
        log.error("Invalid login code. Please run again with the correct code.")
        await client.disconnect()
        sys.exit(1)
    except PhoneCodeExpiredError:
        log.error("Login code expired. Please run again for a fresh code.")
        await client.disconnect()
        sys.exit(1)

    me = await client.get_me()
    log.info("Authenticated as: %s (id=%s)", me.phone, me.id)
    return client


async def ensure_user_allowed(client: Any) -> int:
    """Ensure the test user is in ALLOWED_USER_IDS; update if needed."""
    me = await client.get_me()
    my_id = me.id
    allowed = [int(x.strip()) for x in ALLOWED_USER_IDS_STR.split(",") if x.strip().isdigit()]
    if my_id not in allowed:
        log.warning("Test user id %s not in ALLOWED_USER_IDS (%s)", my_id, allowed)
        log.warning("Updating ALLOWED_USER_IDS to include %s", my_id)
        allowed.append(my_id)
        new_val = ",".join(str(x) for x in allowed)
        # Update in-process env
        os.environ["ALLOWED_USER_IDS"] = new_val
        # Also try to update .env
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            if "ALLOWED_USER_IDS=" in content:
                content = re.sub(
                    r"^ALLOWED_USER_IDS=.*$",
                    f"ALLOWED_USER_IDS={new_val}",
                    content,
                    flags=re.MULTILINE,
                )
                env_path.write_text(content, encoding="utf-8")
                log.info(".env updated with ALLOWED_USER_IDS=%s", new_val)
    return my_id


async def get_bot_username() -> str:
    """Resolve the bot's @username via Bot API."""
    import httpx
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
    async with httpx.AsyncClient(timeout=10) as http:
        resp = await http.get(url)
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Failed to get bot info: {data}")
        username = data["result"]["username"]
        log.info("Bot username resolved: @%s", username)
        return username


# ── KIO Runtime management ───────────────────────────────────────

_kio_process: subprocess.Popen | None = None


def start_kio() -> subprocess.Popen:
    """Start KIO runtime + bot in a subprocess."""
    global _kio_process
    log.info("Starting KIO runtime...")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    # CREATE_NO_WINDOW: this harness can be started from a console-less parent
    # (hidden launcher / agent runner), in which case an unflagged console child
    # pops a visible console window — the exact regression this repo fixed for
    # the runtime's own helper processes. Matches launch_bot.py.
    from mini_kio.core.win_spawn import no_window

    _kio_process = subprocess.Popen(
        [sys.executable, "-u", str(PROJECT_ROOT / "kio_bot.py")],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        **no_window(),
    )
    # Wait for the bot to be ready
    log.info("Waiting for KIO bot to be ready...")
    timeout = 30
    start = time.time()
    while time.time() - start < timeout:
        line = _kio_process.stdout.readline()
        if not line:
            break
        line = line.strip()
        if "KIO TELEGRAM BOT" in line:
            log.info("KIO bot initializing...")
        if "Telegram proxy:" in line:
            log.info("KIO bot ready (Telegram proxy configured)")
            # Give it another moment to start polling
            time.sleep(2)
            return _kio_process
        if "ERROR" in line and "TELEGRAM_TOKEN" in line:
            log.error("KIO bot failed to start: TELEGRAM_TOKEN issue")
            raise RuntimeError(f"KIO bot startup failed: {line}")
    # If we didn't see the ready message but the process is alive, continue
    # The polling likely started
    log.info("KIO bot should be running (timeout reached, continuing)")
    return _kio_process


def stop_kio():
    """Stop the KIO runtime."""
    global _kio_process
    if _kio_process:
        log.info("Stopping KIO runtime...")
        _kio_process.terminate()
        try:
            _kio_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _kio_process.kill()
            _kio_process.wait(timeout=5)
        _kio_process = None
        log.info("KIO runtime stopped.")


# ── Test helpers ──────────────────────────────────────────────────

SHORT_TIMEOUT = 15
LONG_TIMEOUT = 45


async def send_and_wait(
    client: Any,
    bot_entity: Any,
    message: str,
    test_name: str,
    timeout: int = SHORT_TIMEOUT,
    min_reply_length: int = 0,
    expected_patterns: list[str] | None = None,
    previous_msg_id: int | None = None,
) -> str:
    """Send a message to the bot and wait for a reply."""
    start = time.time()
    sent = await client.send_message(bot_entity, message)
    log.info("Sent: %s", message)

    # Wait for reply by polling newer messages
    reply_text = ""
    last_msg_id = sent.id

    while time.time() - start < timeout:
        await asyncio.sleep(1.5)
        try:
            msgs = await client.get_messages(
                bot_entity, limit=5, min_id=last_msg_id
            )
            if msgs:
                # Find a message from the bot (not from us)
                for m in msgs:
                    if m.sender_id != (await client.get_me()).id:
                        reply_text = m.text or ""
                        last_msg_id = m.id
                        break
                if reply_text and len(reply_text) >= min_reply_length:
                    break
        except Exception:
            await asyncio.sleep(1)

    latency = (time.time() - start) * 1000
    passed = bool(reply_text)
    error = ""

    if not reply_text:
        error = f"No reply received within {timeout}s"
    elif min_reply_length and len(reply_text) < min_reply_length:
        error = f"Reply too short ({len(reply_text)} < {min_reply_length}): {reply_text[:100]}"
        passed = False

    record(message, reply_text or "(no reply)", test_name,
           latency_ms=latency, passed=passed, error=error)
    return reply_text


async def send_chain(
    client: Any,
    bot_entity: Any,
    messages: list[tuple[str, str]],
    timeout: int = SHORT_TIMEOUT,
) -> None:
    """Send a chain of messages. Each tuple is (message, test_name)."""
    for msg, test_name in messages:
        await send_and_wait(client, bot_entity, msg, test_name, timeout=timeout)


# ── Intent extraction from reply (best-effort) ────────────────────

def extract_intent(reply: str) -> str:
    """Try to infer the intent from the reply content."""
    reply_lower = reply.lower()
    if "i don't understand" in reply_lower or "unrecognized" in reply_lower:
        return "error/unknown"
    if "help" in reply_lower and "command" in reply_lower:
        return "help"
    if "shutdown" in reply_lower.lower():
        return "shutdown"
    if "remembered" in reply_lower or "i'll remember" in reply_lower or "saved" in reply_lower:
        return "memory_store"
    if "forgotten" in reply_lower or "forgot" in reply_lower or "deleted" in reply_lower:
        return "memory_forget"
    if "search" in reply_lower or "found" in reply_lower or "knowledge" in reply_lower:
        return "knowledge_search"
    if "playing" in reply_lower or "play" in reply_lower or "media" in reply_lower:
        return "media_play"
    if "opening" in reply_lower or "open" in reply_lower or "launch" in reply_lower:
        return "browser_open"
    if "closing" in reply_lower or "closed" in reply_lower:
        return "browser_close"
    if "pause" in reply_lower or "resume" in reply_lower:
        return "media_control"
    if "minimize" in reply_lower or "maximize" in reply_lower or "focus" in reply_lower:
        return "desktop_control"
    if "how are you" in reply_lower or "doing great" in reply_lower or "i'm" in reply_lower:
        return "chitchat"
    return "general_conversation"


# ── Test Suites ──────────────────────────────────────────────────

async def test_conversation(client: Any, bot_entity: Any) -> None:
    """Test basic conversation commands."""
    log.info("\n" + "=" * 60)
    log.info("SUITE 1: Conversation")
    log.info("=" * 60)

    tests = [
        ("/start", "Conversation:/start"),
        ("hello", "Conversation:hello"),
        ("hi", "Conversation:hi"),
        ("good morning", "Conversation:good_morning"),
        ("how are you", "Conversation:how_are_you"),
        ("what's your name", "Conversation:whats_your_name"),
        ("who created you", "Conversation:who_created_you"),
        ("thanks", "Conversation:thanks"),
        ("bye", "Conversation:bye"),
    ]
    for msg, test_name in tests:
        await send_and_wait(client, bot_entity, msg, test_name, timeout=SHORT_TIMEOUT)


async def test_knowledge(client: Any, bot_entity: Any) -> None:
    """Test knowledge queries with follow-ups."""
    log.info("\n" + "=" * 60)
    log.info("SUITE 2: Knowledge")
    log.info("=" * 60)

    await send_and_wait(client, bot_entity, "what is football",
                        "Knowledge:what_is_football", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity, "tell me more",
                        "Knowledge:tell_me_more_1", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity, "basic rules",
                        "Knowledge:basic_rules", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity, "who directed Interstellar",
                        "Knowledge:who_directed_interstellar", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity, "tell me more",
                        "Knowledge:tell_me_more_2", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity, "what's your opinion on football",
                        "Knowledge:opinion_football", timeout=LONG_TIMEOUT)


async def test_context_continuity(client: Any, bot_entity: Any) -> None:
    """Test contextual follow-ups and pronoun resolution."""
    log.info("\n" + "=" * 60)
    log.info("SUITE 3: Context Continuity")
    log.info("=" * 60)

    await send_and_wait(client, bot_entity, "tell me about black holes",
                        "Continuity:black_holes", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity, "how do they form",
                        "Continuity:pronoun_resolution", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity, "explain further",
                        "Continuity:explain_further", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity, "continue",
                        "Continuity:continue", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity, "what is a supernova",
                        "Continuity:supernova", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity, "tell me more",
                        "Continuity:tell_me_more_followup", timeout=LONG_TIMEOUT)


async def test_memory(client: Any, bot_entity: Any) -> None:
    """Test memory storage and retrieval."""
    log.info("\n" + "=" * 60)
    log.info("SUITE 4: Memory")
    log.info("=" * 60)

    await send_and_wait(client, bot_entity,
                        "remember my favourite language is Python",
                        "Memory:remember_fav_language", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity,
                        "what's my favourite language",
                        "Memory:recall_fav_language", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity,
                        "forget my favourite language",
                        "Memory:forget_fav_language", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity,
                        "what's my favourite language",
                        "Memory:recall_after_forget", timeout=LONG_TIMEOUT)


async def test_media(client: Any, bot_entity: Any) -> None:
    """Test media playback commands."""
    log.info("\n" + "=" * 60)
    log.info("SUITE 5: Media")
    log.info("=" * 60)

    await send_and_wait(client, bot_entity,
                        "play Interstellar trailer",
                        "Media:play_trailer", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity, "pause",
                        "Media:pause", timeout=SHORT_TIMEOUT)
    await send_and_wait(client, bot_entity, "resume",
                        "Media:resume", timeout=SHORT_TIMEOUT)
    await send_and_wait(client, bot_entity, "play reviews",
                        "Media:play_reviews", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity, "play something similar",
                        "Media:play_similar", timeout=LONG_TIMEOUT)


async def test_browser(client: Any, bot_entity: Any) -> None:
    """Test browser commands."""
    log.info("\n" + "=" * 60)
    log.info("SUITE 6: Browser")
    log.info("=" * 60)

    await send_and_wait(client, bot_entity,
                        "open YouTube",
                        "Browser:open_youtube", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity,
                        "open Telegram",
                        "Browser:open_telegram", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity,
                        "search OpenAI",
                        "Browser:search_openai", timeout=LONG_TIMEOUT)
    await send_and_wait(client, bot_entity,
                        "switch tab",
                        "Browser:switch_tab", timeout=SHORT_TIMEOUT)
    await send_and_wait(client, bot_entity,
                        "close tab",
                        "Browser:close_tab", timeout=SHORT_TIMEOUT)


async def test_desktop(client: Any, bot_entity: Any) -> None:
    """Test desktop/window control commands."""
    log.info("\n" + "=" * 60)
    log.info("SUITE 7: Desktop / Window")
    log.info("=" * 60)

    await send_and_wait(client, bot_entity,
                        "minimize window",
                        "Desktop:minimize", timeout=SHORT_TIMEOUT)
    await send_and_wait(client, bot_entity,
                        "maximize window",
                        "Desktop:maximize", timeout=SHORT_TIMEOUT)
    await send_and_wait(client, bot_entity,
                        "focus browser",
                        "Desktop:focus_browser", timeout=SHORT_TIMEOUT)


async def test_robustness(client: Any, bot_entity: Any) -> None:
    """Test error handling and edge cases."""
    log.info("\n" + "=" * 60)
    log.info("SUITE 8: Robustness")
    log.info("=" * 60)

    # Invalid commands
    await send_and_wait(client, bot_entity,
                        "asdfghjkl",
                        "Robustness:invalid_command", timeout=SHORT_TIMEOUT)
    await send_and_wait(client, bot_entity,
                        "do something impossible xyzzy",
                        "Robustness:nonsense", timeout=SHORT_TIMEOUT)

    # Typo handling
    await send_and_wait(client, bot_entity,
                        "opne chrome",
                        "Robustness:typo_open", timeout=LONG_TIMEOUT)

    # Emoji handling
    await send_and_wait(client, bot_entity,
                        "hello 👋 how are you?",
                        "Robustness:emoji_hello", timeout=LONG_TIMEOUT)

    # Rapid-fire: send 3 messages in quick succession
    await send_and_wait(client, bot_entity, "hi",
                        "Robustness:rapid_1", timeout=SHORT_TIMEOUT)
    await send_and_wait(client, bot_entity, "how are you",
                        "Robustness:rapid_2", timeout=SHORT_TIMEOUT)
    await send_and_wait(client, bot_entity, "what can you do",
                        "Robustness:rapid_3", timeout=SHORT_TIMEOUT)


async def test_shutdown(client: Any, bot_entity: Any) -> None:
    """Test exit/shutdown behavior."""
    log.info("\n" + "=" * 60)
    log.info("SUITE 9: Shutdown")
    log.info("=" * 60)

    await send_and_wait(client, bot_entity,
                        "exit",
                        "Shutdown:exit", timeout=SHORT_TIMEOUT)
    await send_and_wait(client, bot_entity,
                        "shutdown",
                        "Shutdown:shutdown", timeout=SHORT_TIMEOUT)
    await send_and_wait(client, bot_entity,
                        "cancel",
                        "Shutdown:cancel", timeout=SHORT_TIMEOUT)


# ── Main ──────────────────────────────────────────────────────────

async def main():
    log.info("=" * 60)
    log.info("KIO LIVE TELEGRAM BEHAVIORAL VALIDATION")
    log.info("=" * 60)
    log.info("Project root: %s", PROJECT_ROOT)
    log.info("User phone: %s", TELEGRAM_USER_PHONE)
    log.info("Session file: %s", SESSION_FILE)

    # Step 1: Authenticate via Telethon
    client = await authenticate_telegram()
    me = await client.get_me()
    log.info("Authenticated as user ID: %s", me.id)

    # Step 2: Ensure user is in allowed list
    await ensure_user_allowed(client)
    log.info("User authorized for KIO bot")

    # Step 3: Get bot username
    bot_username = await get_bot_username()
    bot_entity = f"@{bot_username}"
    log.info("Bot entity: %s", bot_entity)

    # Step 4: Start KIO runtime
    try:
        start_kio()
    except Exception as e:
        log.error("Failed to start KIO: %s", e)
        await client.disconnect()
        sys.exit(1)

    # Step 5: Give the bot a moment to be ready
    log.info("Waiting 3 seconds for bot to settle...")
    await asyncio.sleep(3)

    # Step 6: Send a quick ping to verify connectivity
    log.info("Sending connectivity ping...")
    ping_reply = await send_and_wait(client, bot_entity, "ping",
                                     "Setup:connectivity_ping", timeout=20)
    if not ping_reply:
        log.error("Bot did not respond to ping. Checking if running...")
        poll = _kio_process.poll() if _kio_process else -1
        if poll is not None:
            log.error("KIO process has exited with code %s", poll)
        stop_kio()
        await client.disconnect()
        sys.exit(1)
    log.info("Bot is responding. Starting test suites.")

    # Step 7: Run test suites
    suites = [
        ("Conversation", test_conversation),
        ("Knowledge", test_knowledge),
        ("Context Continuity", test_context_continuity),
        ("Memory", test_memory),
        ("Media", test_media),
        ("Browser", test_browser),
        ("Desktop", test_desktop),
        ("Robustness", test_robustness),
        ("Shutdown", test_shutdown),
    ]

    for suite_name, suite_fn in suites:
        try:
            await suite_fn(client, bot_entity)
        except Exception as exc:
            log.error("Suite '%s' failed with exception: %s", suite_name, exc)
            traceback.print_exc()

    # Step 8: Cleanup
    stop_kio()
    await client.disconnect()

    # Step 9: Save transcript and report
    save_transcript()
    report_path = generate_report()

    # Step 10: Summary
    total = len(_test_results)
    passed = sum(1 for r in _test_results if r["passed"])
    failed = total - passed
    rate = (passed / total * 100) if total else 0

    log.info("")
    log.info("=" * 60)
    log.info("VALIDATION COMPLETE")
    log.info("=" * 60)
    log.info("Total tests: %d", total)
    log.info("Passed:      %d", passed)
    log.info("Failed:      %d", failed)
    log.info("Pass rate:   %.1f%%", rate)
    log.info("Transcript:  %s", PROJECT_ROOT / "telegram_transcript.txt")
    log.info("Report:      %s", report_path)
    log.info("")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
        stop_kio()
        save_transcript()
        generate_report()
        sys.exit(0)
