"""
Mini-KIO AI layer: Groq (primary), then optional Claude / Gemini fallbacks.

Responses are plain text only; the rest of the app never executes model output.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from .config import (
    AI_MAX_REPLY_CHARS,
    AI_MAX_TOKENS,
    AI_TEMPERATURE,
    CLAUDE_API_KEY,
    GEMINI_API_KEY,
    GROQ_API_KEY,
    GROQ_MODEL,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

TIMEOUT = 30.0

_CTRL_EXCEPT = frozenset("\n\t\r")


def _log_ai(evt: str, **fields: Any) -> None:
    payload: dict[str, Any] = {"evt": evt}
    payload.update(fields)
    logger.warning(json.dumps(payload, default=str))


def sanitize_ai_response(text: str) -> str:
    """
    Remove NUL / most C0 controls and cap length before Telegram or DB storage.

    Does not execute or interpret content. Shell-style fenced blocks are relabeled to ``text``.
    """
    if not text:
        return ""
    out: list[str] = []
    for ch in text:
        if ch == "\x00":
            continue
        o = ord(ch)
        if o < 32 and ch not in _CTRL_EXCEPT:
            continue
        out.append(ch)
    s = "".join(out)
    s = re.sub(r"(?im)^\s*```(?:bash|sh|zsh|powershell|cmd)\s*\n", "```text\n", s)
    return s[:AI_MAX_REPLY_CHARS]


def _build_messages(
    prompt: str,
    history: Sequence[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """OpenAI-style messages: last eight history turns plus the current user prompt."""
    messages: list[dict[str, str]] = []
    if history:
        for msg in history[-8:]:
            role = msg.get("role")
            content = msg.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": str(role), "content": str(content)})
    messages.append({"role": "user", "content": prompt})
    return messages


def _ask_groq(prompt: str, history: Sequence[dict[str, Any]] | None) -> str:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set")

    messages = _build_messages(prompt, history)

    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    *messages,
                ],
                "max_tokens": AI_MAX_TOKENS,
                "temperature": AI_TEMPERATURE,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return sanitize_ai_response(data["choices"][0]["message"]["content"].strip())


def _ask_claude(prompt: str, history: Sequence[dict[str, Any]] | None) -> str:
    if not CLAUDE_API_KEY:
        raise ValueError("CLAUDE_API_KEY not set")

    messages = _build_messages(prompt, history)

    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.post(
            CLAUDE_API_URL,
            headers={
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": AI_MAX_TOKENS,
                "system": SYSTEM_PROMPT,
                "messages": messages,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return sanitize_ai_response(data["content"][0]["text"].strip())


def _ask_gemini(prompt: str, history: Sequence[dict[str, Any]] | None) -> str:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")

    contents: list[dict[str, Any]] = []
    if history:
        for msg in history[-8:]:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]})

    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={"contents": contents},
        )
        resp.raise_for_status()
        data = resp.json()
        return sanitize_ai_response(data["candidates"][0]["content"]["parts"][0]["text"].strip())


def ask_ai(prompt: str, history: list[dict[str, Any]] | None = None) -> str:
    """
    Call configured providers in order (Groq → Claude → Gemini) until one succeeds.

    ``history`` is optional chat context from SQLite; entries missing ``role``/``content`` are skipped.
    """
    providers: list[tuple[str, Callable[[str, Sequence[dict[str, Any]] | None], str]]] = []

    if GROQ_API_KEY:
        providers.append(("Groq", _ask_groq))
    if CLAUDE_API_KEY:
        providers.append(("Claude", _ask_claude))
    if GEMINI_API_KEY:
        providers.append(("Gemini", _ask_gemini))

    if not providers:
        return "No API keys configured. Add GROQ_API_KEY to your environment."

    last_error: str | None = None
    for name, fn in providers:
        try:
            logger.debug(
                json.dumps({"evt": "ai_try", "provider": name}),
            )
            result = fn(prompt, history)
            logger.debug(
                json.dumps({"evt": "ai_ok", "provider": name}),
            )
            return result
        except httpx.HTTPStatusError as e:
            last_error = f"{name} HTTP {e.response.status_code}"
            _log_ai("ai_provider_http_error", provider=name, status=e.response.status_code)
        except Exception as e:
            last_error = f"{name}: {type(e).__name__}"
            _log_ai("ai_provider_error", provider=name, error_type=type(e).__name__)

    return f"All AI providers failed. Last error: {last_error}"


def generate_code(description: str) -> str:
    """Ask the model for code only (brief comments); same provider chain as ``ask_ai``."""
    prompt = (
        f"Write clean, working code for: {description}\n"
        "Include only the code and brief comments. No lengthy explanation."
    )
    return ask_ai(prompt)
