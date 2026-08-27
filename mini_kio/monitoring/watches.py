"""
mini_kio/monitoring/watches.py — General Watch/Monitor (canonical owner)

One general monitoring mechanism with interchangeable PROBES:

  - 'watch openai/openai for new releases'  -> feed probe (GitHub releases.atom)
  - 'watch requests'                        -> feed probe (PyPI release RSS)
  - 'watch https://example.com'             -> page probe (content fingerprint)
  - 'watch example.com'                     -> page probe (fingerprint, https)

A background poller checks each target's probe; when the probe's fingerprint
CHANGES (a newer release appears, or the page content changes), a message is
pushed out-of-band (Telegram sendMessage) — no prompt needed. Baseline-at-add
means existing state never spams the user; only real changes notify.

The feed probes reuse the utilities owner (_http_get_bytes / _parse_feed_items
/ _feed_url_for_target) so the 'what's new' answer and the watcher can never
disagree about a target's feed. The page probe is a general content
fingerprint (normalized visible text hash) — ONE page monitor, not one per
site kind.
"""

import hashlib
import logging
import re
import urllib.parse
from typing import Dict

from mini_kio.backend.repositories.watch_repository import WatchRepository
from mini_kio.core.config import TELEGRAM_TOKEN
from mini_kio.core import utilities

logger = logging.getLogger(__name__)

_repo = WatchRepository()

# ponytail: fixed 60s poll cadence + no retry/backoff on Telegram failure —
# a watcher tolerates a skipped tick. Add per-watch intervals and backoff
# when throughput or delivery reliability starts to matter.
POLL_INTERVAL_S = 60.0

# ── probe kinds (one mechanism, interchangeable probes) ─────────────────────
# Stored kind is the PROBE SUBKIND so existing rows/contracts stay valid:
#   github | pypi  -> release-feed probe (structured newest item)
#   page           -> arbitrary http(s) URL, content fingerprint
_KIND_PAGE = "page"
_FEED_KINDS = frozenset({"github", "pypi", "feed"})  # "feed" = legacy alias


def _watch_kind(target: str):
    """Classify a watch target into (kind, probe_url):

      owner/repo        -> github (GitHub releases.atom feed)
      bare package name -> pypi (PyPI release RSS feed)
      http(s)://...     -> page (fingerprint the URL itself)
      domain.tld        -> page (fingerprint https://domain.tld)
    """
    t = (target or "").strip()
    low = t.lower()
    if low.startswith(("http://", "https://")):
        return _KIND_PAGE, t
    if "/" in t:
        return "github", t
    # A bare dotted name (example.com) is a page target — never a PyPI
    # package. Only undotted single tokens resolve to PyPI.
    if re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", low):
        return _KIND_PAGE, "https://" + t
    return "pypi", t


# ── outbound delivery (the one push channel KIO has) ────────────────────────
def send_telegram_message(chat_id: str, text: str) -> bool:
    """Push a message to a Telegram chat via the Bot API. Returns True only
    when Telegram confirmed delivery. Never raises on failure."""
    if not TELEGRAM_TOKEN:
        logger.info("[WATCH_PUSH] no TELEGRAM_TOKEN configured — skip push")
        return False
    if not chat_id:
        return False
    try:
        import urllib.request
        url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN)
        data = urllib.parse.urlencode(
            {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
        ).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10.0) as r:
            body = r.read().decode("utf-8", "replace")
        ok = '"ok":true' in body
        logger.info("[WATCH_PUSH] chat_id=%s delivered=%s", chat_id, ok)
        return ok
    except Exception as exc:
        logger.warning("[WATCH_PUSH] delivery failed chat_id=%s: %s", chat_id, exc)
        return False


# ── target parsing ───────────────────────────────────────────────────────────
# "watch it"/"watch this" are media offer-acceptance, NOT release-watching —
# those pronoun-only targets must never classify as a watch.
_WATCH_STOP = {"the", "a", "an", "to", "for", "of", "new", "releases", "release",
               "watch", "watching", "please", "on", "me", "us", "updates", "update",
               "it", "this", "that", "them", "those", "they", "now", "again",
               "later", "here", "there"}


def _clean_target(t: str) -> str:
    t = t.strip(" ./!?;:,").strip()
    return t if t and t not in _WATCH_STOP else ""


# Opinion/recommendation questions that merely contain the word "watch"
# ("should i watch dune", "would you watch it", "what movie should I watch
# tonight", "recommend something to watch") are NEVER watch registrations —
# they are conversational preference questions. A watch command must HEAD the
# utterance with the monitoring intent ("watch X"); any interrogative/modal
# opener with a later "watch" is a question, not a command. Morphological
# guard, not a phrase list.
_WATCH_QUESTION_RE = re.compile(
    r"^(?:should|would|could|can|shall|do|does|did|are|is|was|were|what|which|"
    r"why|how|recommend|suggest|want\s+me\s+to|need\s+me\s+to|can\s+you|i\s+want\s+to)\b.*\bwatch\b",
    re.I,
)


# General monitoring vocabulary — the same mechanism, more phrasings:
#   watch X / keep an eye on X / monitor X / track X / watch X for changes
# are ALL registrations. "watch" is the canonical verb; the others are
# natural monitoring phrasings for the SAME primitive (never per-domain).
_WATCH_ADD_RE = re.compile(
    r"\b(?:watch|keep\s+an\s+eye\s+on|keep\s+watching|monitor|track)\s+"
    r"([^\s]+(?:\s+[^\s]+)*?)",
    re.I,
)


def _extract_watch_command(query: str):
    """Returns (sub_action, target) for the watch family:
       watch X / keep an eye on X / monitor X  -> ("add", X)
       stop watching X / unwatch X             -> ("remove", X)
       what am i watching / list my watches    -> ("list", "")
    """
    low = query.lower().strip()
    if _WATCH_QUESTION_RE.search(low):
        return None, ""
    if re.search(r"what\s+am\s+i\s+watching|list\s+my\s+watches|show\s+my\s+watches|my\s+watches", low):
        return "list", ""
    m = re.search(r"stop\s+watching\s+([^\s]+(?:\s+[^\s]+)*?)", low)
    if m:
        return "remove", _clean_target(m.group(1))
    m = re.search(r"unwatch\s+([^\s]+(?:\s+[^\s]+)*?)", low)
    if m:
        return "remove", _clean_target(m.group(1))
    m = _WATCH_ADD_RE.search(low)
    if m:
        t = _clean_target(m.group(1))
        # strip trailing intent qualifiers: 'for new releases' / 'for changes'
        t = re.sub(r"\s+for\s+(?:new\s+)?(?:releases|changes|updates)\s*$", "", t, flags=re.I).strip()
        # trailing stopwords after the target ('watch requests now',
        # 'keep an eye on openai please') are not part of the target
        t = re.sub(r"\s+(?:now|please|today|tomorrow|here|later)\s*$", "", t, flags=re.I).strip()
        return ("add", t) if t else (None, "")
    return None, ""


def looks_like_watch(query: str) -> bool:
    """Routing hook: True for the watch/stop-watching/list-watches family."""
    # Media-play guard: "watch X in chrome" / "watch X on YouTube" /
    # "watch X in browser" / "watch the trailer" are MEDIA commands,
    # not monitoring registrations. The browser/platform suffix and the
    # media-noun context distinguish them from feed watches.
    low = query.lower().strip()
    _MEDIA_WATCH_GUARD = re.search(
        r"\b(?:in\s+(?:chrome|edge|firefox|brave|browser|the\s+browser)|"
        r"on\s+(?:youtube|the\s+web|a\s+browser)|"
        r"trailer|movie|video|interview|episode|concert|show|stream|"
        r"performance|lecture|tutorial|documentary|live)\b",
        low,
    )
    if _MEDIA_WATCH_GUARD:
        return False
    action, target = _extract_watch_command(query)
    if action == "list":
        return True
    return action in ("add", "remove") and bool(target)


def _page_fingerprint(url: str):
    """(key, items) for a page probe — key is a fingerprint of the page's
    NORMALIZED visible text (stable across headers/timestamps; sensitive to
    real content change). Returns (None, []) when the page is unreachable."""
    raw = utilities._http_get_bytes(url, timeout=8.0)
    if raw is None:
        return None, []
    try:
        text = raw.decode("utf-8", "replace")
    except Exception:
        return None, []
    # Strip script/style/nav noise, collapse whitespace, lowercase — the
    # fingerprint tracks MEANINGFUL content change, not byte churn.
    text = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    norm = " ".join(text.lower().split())
    if len(norm) < 20:
        return None, []
    key = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    title_m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw.decode("utf-8", "replace"))
    title = title_m.group(1).strip()[:120] if title_m else url
    return key, [(title, url, "")]


def _fetch_latest(target: str, kind: str):
    """(key, items) for a target+kind via its probe.
    Returns (None, []) when the probe is unreachable.

    `target` is the USER-FACING watch target ("example.com"), so the probe
    is resolved through `_watch_kind` here — a page probe needs the full
    https URL, and the poller must never hand a bare domain to the fetcher.
    """
    if kind == _KIND_PAGE:
        _k, probe = _watch_kind(target)
        return _page_fingerprint(probe)
    # feed probes (github | pypi | legacy "feed") share the utilities feed
    # resolution so the 'what's new' answer and the watcher agree on the
    # target's feed.
    url, _subkind = utilities._feed_url_for_target(target)
    items = utilities._parse_feed_items(utilities._http_get_bytes(url) or b"", limit=5)
    if not items:
        return None, []
    title, link, date = items[0]
    return f"{title}|{link}", items


def _describe(target: str, kind: str) -> str:
    if kind == _KIND_PAGE:
        return target
    url, subkind = utilities._feed_url_for_target(target)
    label = f"{target} (GitHub)" if subkind == "github" else f"{target} (PyPI)"
    return label


# ── user-facing answer ───────────────────────────────────────────────────────
def watch_answer(query: str, ctx=None, decision=None) -> dict:
    """Canonical watch owner: 'watch X for new releases' / 'stop watching X' /
    'what am I watching'. Persists to the watches table; the background
    poller does the actual push."""
    action, target = _extract_watch_command(query)
    chat_id, channel, user_id = _delivery_ids(decision)

    if action == "list":
        rows = _repo.list_active(chat_id)
        if not rows:
            return {"success": True, "message": "You're not watching anything right now.",
                    "type": "watch", "action": "list", "watches": []}
        parts = [f"{r['target']} ({r['kind']})" for r in rows]
        return {"success": True,
                "message": "You're watching: " + "; ".join(parts) + ".",
                "type": "watch", "action": "list", "watches": rows}

    if action == "remove":
        if not target:
            return {"success": False, "message": "Tell me what to stop watching — like 'stop watching requests'.",
                    "type": "watch", "action": "remove"}
        # Canonical key: 'stop watching example.com' must match a watch
        # registered as 'https://example.com' — both resolve to the same
        # probe URL, so removal looks up by the canonical key, never by the
        # user's surface spelling.
        _k, _probe = _watch_kind(target)
        _lookup = _probe if _k == _KIND_PAGE else target
        ok = _repo.deactivate(_lookup, chat_id)
        return {"success": ok,
                "message": f"Stopped watching {target}." if ok else f"You weren't watching {target}.",
                "type": "watch", "action": "remove", "target": target}

    if action == "add":
        if not target:
            return {"success": False,
                    "message": "Tell me what to watch — like 'watch openai/openai for new releases' or 'watch example.com'.",
                    "type": "watch", "action": "add"}
        kind, probe = _watch_kind(target)
        key, _items = _fetch_latest(probe, kind)
        if key is None:
            return {"success": False, "watch": target,
                    "message": f"I couldn't reach {_describe(target, kind)} — nothing to watch yet.",
                    "type": "watch", "action": "add"}
        # Store the CANONICAL key (probe URL for page targets) so add and
        # remove always agree regardless of surface spelling (https:// vs
        # bare domain, trailing slash).
        _stored = probe if kind == _KIND_PAGE else target
        _repo.add(_stored, kind, chat_id, channel=channel, user_id=user_id, last_seen_key=key)
        if kind == _KIND_PAGE:
            note = "I'll notify you here when the page content changes."
        else:
            note = "I'll notify you here when a new release appears."
        return {"success": True,
                "message": f"Watching {_describe(target, kind)}. {note}",
                "type": "watch", "action": "add", "target": target, "kind": kind,
                "baseline": key}

    return {"success": False,
            "message": "Tell me what to watch — like 'watch openai/openai for new releases'.",
            "type": "watch"}


def _delivery_ids(decision):
    if decision is not None:
        channel = getattr(decision, "channel", "") or ""
        user_id = getattr(decision, "user_id", 0) or 0
        if channel == "telegram" and user_id:
            return str(user_id), channel, str(user_id)
        return "terminal", channel, str(user_id)
    return "terminal", "unknown", ""


# ── background poller (called by the runtime host thread) ────────────────────
def poll_watches() -> Dict[str, int]:
    """Check every active watch; push a Telegram message for each watch whose
    probe fingerprint changed since its baseline. Returns {checked, notified}.

    One loop, one diff (fingerprint != baseline), one notify — the probe
    kind only changes WHAT the message says, never the mechanism."""
    checked, notified = 0, 0
    for watch in _repo.all_active():
        checked += 1
        kind = watch.kind or "pypi"
        if kind not in _FEED_KINDS and kind != _KIND_PAGE:
            kind = "pypi"
        # github / pypi / legacy "feed" all dispatch through the feed probe;
        # only "page" uses the fingerprint probe.
        key, items = _fetch_latest(watch.target, kind)
        if key is None:
            continue
        if not watch.last_seen_key:
            # First successful fetch after a registration-time failure: just
            # baseline, never dump existing state at the user.
            _repo.update_last_seen(watch.id, key)
            continue
        if key != watch.last_seen_key:
            title, link, _date = items[0]
            label = _describe(watch.target, kind)
            if kind == _KIND_PAGE:
                text = f"The page you're watching changed: {label}"
                if link:
                    text += f"\n{link}"
            else:
                text = f"New release: {title} ({label})"
                if link:
                    text += f"\n{link}"
            if send_telegram_message(watch.chat_id, text):
                notified += 1
            _repo.update_last_seen(watch.id, key)
            # Buffer as away event for return-surfacing
            try:
                from mini_kio.core.activation import record_away_event
                record_away_event(
                    source="watch",
                    description=f"Watched feed '{watch.target}' has a new update: {title}",
                    urgency="medium",
                )
            except Exception:
                pass
            logger.info("[WATCH_POLL] target=%s kind=%s new=%s notified=%s",
                        watch.target, kind, title, notified)
    return {"checked": checked, "notified": notified}