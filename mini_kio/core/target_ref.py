"""
target_ref.py — Canonical Target Identity (BC-1/BC-3/BC-5 fix)

The execution pipeline used to thread a single `str target` where target kinds
(application / browser / tab / web-app / media / file) were conflated and
serialized capability strings (`chrome::open_url::https://chat.openai.com::chatgpt`)
were treated as user-facing targets.

This module is the ONE canonical place that:
  1. Parses serialized capability strings back into structured target refs.
  2. Produces a user-safe display name (never leaks URLs / :: chains / internal ids).
  3. Classifies a raw target string by kind so consumers (close_app, formatters,
     context referents) act at the correct scope.

Consumers MUST use safe_target_name() for anything that reaches a user, and
parse_target() before deciding execution scope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TargetRef:
    """Structured target identity that survives resolution -> execution -> response."""

    kind: str  # "app" | "browser" | "tab" | "webapp" | "media" | "file" | "unknown"
    name: str  # canonical/friendly name, e.g. "chatgpt"
    browser: str = ""  # host browser for webapp/tab targets ("chrome", ...)
    url: str = ""  # resolved URL (internal artifact, never user-facing by default)
    pid: Optional[int] = None
    capability: str = ""  # raw capability id when this ref came from one
    raw: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "browser": self.browser,
            "url": self.url,
            "pid": self.pid,
            "capability": self.capability,
        }


_CAP_RE = re.compile(
    r"^(?P<browser>[a-z0-9_\-]+)::(?P<cap>[a-z_]+)::(?P<arg>.+?)(?:::(?P<name>[^:]+))?$",
    re.IGNORECASE,
)

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# Registered web apps that resolve to browser tabs even though they have no
# native registry entry (chatgpt/telegram/whatsapp/...).
_WEBAPP_HINTS = frozenset({
    "chatgpt", "telegram", "whatsapp", "youtube", "gmail", "instagram",
    "facebook", "github", "reddit", "twitter", "x", "spotify", "netflix",
    "claude", "gemini", "google", "maps", "drive", "docs", "outlook",
})

_BROWSER_NAMES = frozenset({
    "chrome", "edge", "firefox", "brave", "comet", "opera", "browser",
})


def parse_target(raw: str) -> TargetRef:
    """Parse any raw target string into a structured TargetRef.

    Handles:
      - serialized capability strings: "chrome::open_url::https://...::chatgpt"
      - plain web-app names: "chatgpt", "telegram"
      - browser names: "chrome", "edge"
      - URLs: "https://chat.openai.com"
      - everything else: treated as a generic app/name string.
    """
    raw = (raw or "").strip()
    if not raw:
        return TargetRef(kind="unknown", name="", raw=raw)

    m = _CAP_RE.match(raw)
    if m:
        browser = m.group("browser").lower()
        cap = m.group("cap").lower()
        arg = m.group("arg").strip()
        name = (m.group("name") or "").strip()
        if cap == "open_url":
            kind = "webapp"
            name = name or _name_from_url(arg) or browser
        elif cap in ("play", "search", "youtube"):
            kind = "webapp" if cap == "search" else "media"
            name = name or arg
        else:
            kind = "tab"
            name = name or browser
        return TargetRef(
            kind=kind,
            name=name.lower(),
            browser=browser,
            url=arg if _URL_RE.match(arg) else "",
            capability=cap,
            raw=raw,
        )

    low = raw.lower()
    if low in _BROWSER_NAMES:
        return TargetRef(kind="browser", name=low, raw=raw)
    if _URL_RE.match(raw):
        return TargetRef(kind="webapp", name=_name_from_url(raw).lower(), url=raw, raw=raw)
    if low in _WEBAPP_HINTS:
        return TargetRef(kind="webapp", name=low, raw=raw)
    if low.endswith(".exe"):
        return TargetRef(kind="app", name=low[:-4], raw=raw)
    return TargetRef(kind="app", name=low, raw=raw)


def safe_target_name(raw: str) -> str:
    """User-safe display name for a raw target.

    Guarantees: never returns a URL, never returns a `::`-serialized chain,
    never returns an internal capability id. Preserves the original casing so
    media queries / referents keep their natural text — display formatters own
    capitalization.
    """
    ref = parse_target(raw)
    name = ref.name or ref.browser
    if not name:
        return raw or "it"
    return name.replace("_", " ").strip() or "it"


def parse_capability_string(raw: str) -> Optional[dict]:
    """Return the structured parts of a serialized capability string, or None.

    Compat helper for code that already splits on `::` and wants the parts:
        {"browser", "capability", "arg", "name", "url"}
    """
    ref = parse_target(raw)
    if not ref.capability:
        return None
    return {
        "browser": ref.browser,
        "capability": ref.capability,
        "arg": ref.url or ref.name,
        "name": ref.name,
        "url": ref.url,
        "kind": ref.kind,
    }


_BRAND_NAMES = {
    "chatgpt": "ChatGPT",
    "whatsapp": "WhatsApp",
    "youtube": "YouTube",
    "google": "Google",
    "gmail": "Gmail",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "github": "GitHub",
    "reddit": "Reddit",
    "twitter": "Twitter",
    "spotify": "Spotify",
    "netflix": "Netflix",
    "claude": "Claude",
    "gemini": "Gemini",
    "telegram": "Telegram",
    "notepad": "Notepad",
    "calculator": "Calculator",
    "chrome": "Chrome",
    "edge": "Edge",
    "firefox": "Firefox",
    "brave": "Brave",
    "comet": "Comet",
    "opera": "Opera",
}


def display_target_name(raw: str) -> str:
    """User-facing, properly-cased name for a raw target.

    Unlike safe_target_name (which preserves lowercase for referents/matching),
    this applies brand casing ("chatgpt" -> "ChatGPT", "youtube" -> "YouTube")
    and first-letter capitalization for display. Never leaks URLs / :: chains.
    """
    safe = safe_target_name(raw)
    low = safe.lower().strip()
    if low in _BRAND_NAMES:
        return _BRAND_NAMES[low]
    if not low:
        return "it"
    return low[0].upper() + low[1:]


def _name_from_url(url: str) -> str:
    """Derive a friendly name from a URL (best-effort, never the raw URL)."""
    try:
        from mini_kio.core.runtime_response_formatter import _extract_url_name
        return _extract_url_name(url)
    except Exception:
        pass
    host = re.sub(r"^https?://", "", url, flags=re.IGNORECASE)
    host = host.split("/")[0]
    host = host.replace("www.", "")
    parts = host.split(".")
    return parts[0].capitalize() if parts else url
