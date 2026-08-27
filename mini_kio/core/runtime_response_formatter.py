"""
runtime_response_formatter.py — Gate 5.1 User-Facing Runtime Response Layer

Converts internal execution results into natural deterministic responses.
Never exposes internal routing names, capability identifiers, fallback terminology,
or execution classifications.
"""

import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

_DIAG: Dict[str, int] = {
    "runtime_response_formatted": 0,
    "response_already_natural": 0,
    "provider_artifact_sanitized": 0,
}

# Provider-UI artifacts that must NEVER reach the user as the KIO reply
# (search-widget controls, time/date widgets, provider chrome). Generic
# patterns — this is a last-resort boundary guard; the source fix is that
# utility/utility-shaped requests are owned deterministically and never
# reach a provider in the first place.
_PROVIDER_UI_RE = re.compile(
    r"\b(related searches|people also ask|more info\b|sign up or log in|"
    r"open result\b|search instead|see more\b|recent searches|"
    r"feedback about|week \d{1,2}\b|sunrise|sunset|favorite locations|"
    r"make \w[\w ]{0,30}? default|remove from (favorite|favourites)|\|\s*more info)",
    re.IGNORECASE,
)
_TIME_WIDGET_RE = re.compile(
    r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE,
)
_TIME_WIDGET_LOC_RE = re.compile(
    r"\btime\s+in\s+([a-z][a-z .'-]{1,40}?)(?:,|\.|\s+now\b|\s+$)", re.IGNORECASE,
)
_DEV_PATTERNS = re.compile(
    r'\b(Routed|search_fallback|capability lookup|execution classification|'
    r'outcome_class|verification_status|failure_class|'
    r'execute_capability|execution_id|tool_version|handler)\b',
    re.IGNORECASE,
)
_PID_PATTERN = re.compile(r'\s*\(pid \d+\)')
_BROWSER_NAME_OVERRIDES = {"chrome": "Chrome", "edge": "Edge", "firefox": "Firefox", "brave": "Brave", "comet": "Comet", "opera": "Opera"}

# Slice 7 (B.1): internal prerequisite identifiers -> natural user language.
# Internal identifiers (browser_backend, credential ids, etc.) must never
# surface; unknown ids collapse to a generic, still-truthful phrase.
_PREREQUISITE_LABELS = {
    "browser_backend": "the browser to be connected",
}
_GENERIC_PREREQUISITE_PHRASE = "some setup before I can do that"

# KIO-authored deterministic result types (utility seam owners): these
# messages are ALREADY the user reply — never provider UI, never re-rendered
# by the artifact sanitizer even when they contain time/date-shaped text.
_KIO_OWNED_TYPES = frozenset({
    "time", "date", "weather", "convert", "package", "feed", "calculate",
    "project", "watch", "reminder", "research", "air_quality", "holiday",
    "earthquake", "book", "utility",
})


_PROVIDER_DISPLAY = {
    "google": "Google",
    "gmail": "Gmail",
    "telegram": "Telegram",
    "github": "GitHub",
    "discord": "Discord",
    "openai": "OpenAI",
    "microsoft": "Microsoft",
    "outlook": "Outlook",
    "spotify": "Spotify",
    "youtube": "YouTube",
}


def _credential_label(prereq_id: str) -> str:
    """Map a `credential:<provider>:<type>[:state]` prerequisite id to natural
    language without leaking internal ids. Slice 9 state-qualified ids (e.g.
    `credential:github:oauth2:expired`) render the truthful reason."""
    parts = prereq_id.split(":")
    if len(parts) >= 3 and parts[0] == "credential":
        provider = parts[1]
        cred_type = parts[2]
        type_word = cred_type.replace("_", " ")
        display_provider = _PROVIDER_DISPLAY.get(provider.lower(), provider.capitalize())
        noun = f"your {display_provider} {type_word} credentials"
        state = parts[3] if len(parts) >= 4 else ""
        if state == "expired":
            return f"{noun} to be reconnected (they've expired)"
        if state == "revoked":
            return f"{noun} to be reconnected (they were revoked)"
        if state == "unavailable":
            return f"{noun} to be reconnected (they're unavailable)"
        return noun
    return ""


def reset_diag():
    _DIAG["runtime_response_formatted"] = 0
    _DIAG["response_already_natural"] = 0


def get_diag() -> Dict[str, int]:
    return dict(_DIAG)


def _extract_url_name(target: str) -> str:
    """Extract a human-readable name from a URL or combined target string."""
    lower = target.lower().strip()
    
    # Deterministic mapping for common web targets (BUG 5)
    KNOWN_DOMAINS = {
        "web.telegram.org": "Telegram",
        "web.whatsapp.com": "WhatsApp",
        "chat.openai.com": "ChatGPT",
        "chatgpt.com": "ChatGPT",
        "claude.ai": "Claude",
        "gemini.google.com": "Gemini",
        "github.com": "GitHub",
        "youtube.com": "YouTube",
        "spotify.com": "Spotify",
        "instagram.com": "Instagram",
        "netflix.com": "Netflix",
        "google.com": "Google",
        "gmail.com": "Gmail"
    }
    
    # Handle capability format: browser::cap::url[::friendly]
    if "::" in lower:
        parts = lower.split("::")
        if len(parts) >= 4:
            return parts[3].capitalize()
        if len(parts) >= 3:
            url_part = parts[-1]
        elif len(parts) == 2:
            return parts[0].capitalize()
        else:
            url_part = parts[0]
    else:
        url_part = lower

    # Strip protocol and trailing slash
    url_part = re.sub(r'^https?://', '', url_part).rstrip('/')
    # Strip www
    url_part = re.sub(r'^www\.', '', url_part)
    
    # Check known domains
    for domain, friendly in KNOWN_DOMAINS.items():
        if url_part == domain or url_part.startswith(domain + "/"):
            return friendly

    # Extract domain root (e.g., "instagram.com" -> "Instagram")
    # Improved: handle subdomains by taking the part before the TLD
    domain_match = re.search(r'([^/.]+)\.(?:com|org|net|ai|io|dev|app|edu|gov)$', url_part)
    if domain_match:
        name = domain_match.group(1)
        return name.capitalize()
    
    # Fallback to first part
    domain_match = re.match(r'([^/.]+)', url_part)
    if domain_match:
        name = domain_match.group(1)
        if name == "web" and "." in url_part:
            # Handle "web.telegram.org" fallback if search failed
            parts = url_part.split(".")
            if len(parts) > 1: return parts[1].capitalize()
        return name.capitalize()
    
    return url_part.capitalize()


def _safe_display_target(target: str) -> str:
    """User-safe display name for a target (BC-5: no raw URLs / :: chains)."""
    from mini_kio.core.target_ref import display_target_name
    return display_target_name(str(target or ""))


def format_open_app(target: str, success: bool, message: str, details: Optional[Dict[str, Any]] = None) -> str:
    if not success:
        return _format_error(_ensure_str(message))
    # UX RULE (2026-08-10 directive): a successful open gets a short natural
    # confirmation ("Opened Stack Overflow.") — including a web fallback.
    # Internal native-vs-web modality stays in the structured details so
    # "close it" still resolves to the correct web target; the user is not
    # burdened with resolver mechanics on success. Failure messages keep their
    # truthful explanation.
    msg = _ensure_str(message).strip()
    # Keep a real natural confirmation ("Opened Stack Overflow.",
    # "Telegram is already open.") verbatim — but never a trivial filler
    # ("ok", "done") that would hide the resolved target name.
    if (
        msg
        and len(msg) > 2
        and msg.lower() not in _TRIVIAL_FILLERS
        and _is_natural(msg)
        and not _contains_dev_terms(msg)
    ):
        return msg
    display = _safe_display_target(target)
    return f"Opened {display}."


def format_close_app(target: str, success: bool, details: Dict[str, Any]) -> str:
    """Translate a structured close outcome into concise user-facing language.

    BUG 7: the response must correspond to the strongest verified state and
    must never contradict itself. Outcome classes from app_operator:
      SUCCESS                -> "Closed X."
      SUCCESS_WITH_RESIDUALS -> "Closed X, but some background processes are
                                 still running." (partial, but concise)
      NOT_RUNNING            -> "X wasn't running."
      FAILED / other         -> truthful failure via the message.
    Implementation detail (pids, process trees, registry names) stays in the
    structured fields and is never surfaced.
    """
    if details.get("capability_closed"):
        cap_name = details.get("capability_name") or _safe_display_target(target)
        return f"Closed {cap_name}."

    display = _safe_display_target(target)
    outcome = str(details.get("outcome_class") or "").upper()
    verification = str(details.get("verification_status") or "").lower()

    if not success:
        msg = _ensure_str(details.get("message", ""))
        if outcome == "NOT_RUNNING" or verification == "not_running" or \
           "not running" in msg.lower() or "wasn't running" in msg.lower() or \
           "was already closed" in msg.lower() or "already closed" in msg.lower():
            return f"{display} wasn't running."
        if "ambiguous" in msg.lower():
            return f"Couldn't close {display}: multiple matches found."
        if "not found" in msg.lower() or "not track" in msg.lower():
            return f"Couldn't find {display} to close."
        return _format_error(msg)

    # Success path — but be truthful about residuals.
    if outcome == "SUCCESS_WITH_RESIDUALS" or verification == "passed_with_residuals" or details.get("residual_pid"):
        return f"Closed {display}, but some background processes are still running."
    return f"Closed {display}."


def format_search(target: str, success: bool, message: str) -> str:
    if not success:
        return _format_error(message)
    if target:
        return f"Searched for {target}."
    return "Search completed."


def format_capability(
    target: str, success: bool, details: Dict[str, Any]
) -> str:
    if not success:
        msg = _ensure_str(details.get("message", ""))
        if "not found" in msg.lower():
            return f"Couldn't open that page."
        if "not support" in msg.lower():
            return f"That action isn't supported."
        return _format_error(msg)
    browser = details.get("browser", "")
    display_browser = _BROWSER_NAME_OVERRIDES.get(browser.lower(), browser.capitalize()) if browser else ""
    cap_name = details.get("capability_name", "")
    if cap_name and display_browser:
        return f"Opened {cap_name} in {display_browser}."
    if display_browser:
        url_name = _extract_url_name(target)
        return f"Opened {url_name} in {display_browser}."
    url_name = _extract_url_name(target)
    return f"Opened {url_name}."


def format_generic_success(target: str, message: str) -> str:
    if _is_natural(message):
        return message
    if target:
        return f"Done. {target.capitalize()}."
    return "Done."


def _ensure_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("status", "")) or str(value)
    return str(value)


def _format_prerequisite(details: Dict[str, Any]) -> str:
    """Slice 7: render a fail-closed prerequisite gate naturally.

    "I need <what> before I can do that." — no internal prerequisite ids,
    class names, or gate metadata. Unknown ids fold into a generic phrase.
    """
    gate = details.get("prerequisite_gate")
    missing = gate.get("missing") if isinstance(gate, dict) else None
    if not missing:
        return "I need some setup before I can do that."
    labels = [
        _PREREQUISITE_LABELS.get(str(m)) or _credential_label(str(m))
        for m in missing
    ]
    labels = [label for label in labels if label]
    if not labels:
        return "I need some setup before I can do that."
    if len(labels) == 1:
        return f"I need {labels[0]} before I can do that."
    if len(labels) == 2:
        return f"I need {labels[0]} and {labels[1]} before I can do that."
    return f"I need {', '.join(labels[:-1])}, and {labels[-1]} before I can do that."


def _sanitize_provider_artifact(message: str) -> str:
    """Last-resort clean-up of raw provider/search/utility UI text.

    Two cases:
      1. Time/date widget ("Time in New York, United States now:
         18:52:09 Thursday, 13 August, 2026, week 33 Sun: ..."): extract the
         actual time and rebuild a clean KIO answer.
      2. Any other provider-UI text: cut at the first UI-control marker so
         KIO never reproduces the provider's interface.
    If nothing useful remains, fall back to an honest short answer — never
    pass the raw UI through.
    """
    if not message:
        return message
    m_loc = _TIME_WIDGET_LOC_RE.search(message)
    m_time = _TIME_WIDGET_RE.search(message)
    if m_time:
        try:
            h, mi = int(m_time.group(1)), int(m_time.group(2))
            suffix = "AM" if h < 12 else "PM"
            h12 = h % 12 or 12
            time_str = f"{h12}:{mi:02d} {suffix}"
            if m_loc:
                loc = m_loc.group(1).strip().title()
                return f"It's {time_str} in {loc}."
            return f"It's {time_str}."
        except Exception:
            pass
    cut = _PROVIDER_UI_RE.search(message)
    if cut:
        prefix = message[: cut.start()].strip()
        prefix = prefix.rstrip(" -|,")
        if len(prefix) > 4 and not _PROVIDER_UI_RE.search(prefix):
            if not prefix[-1:].isalnum():
                prefix = prefix[:-1]
            return prefix + "."
    return "I couldn't pull that up cleanly — try asking me directly."


def format_result(
    action: str, target: str, success: bool, details: Dict[str, Any]
) -> str:
    # Slice 7: a fail-closed prerequisite gate always gets its natural
    # explanation regardless of the operator message.
    if isinstance(details.get("prerequisite_gate"), dict):
        _DIAG["runtime_response_formatted"] += 1
        return _format_prerequisite(details)
    message = _ensure_str(details.get("message", ""))
    # Result-ownership boundary: raw provider/utility UI text must never
    # become the KIO reply. When the message carries provider chrome or a
    # time/date widget, synthesize the clean answer instead of passing the
    # raw text through the "natural message" fast path. KIO's OWN
    # deterministic answers are exempt: they are authored replies that carry
    # a result "type" (watch / reminder / research / air_quality / holiday /
    # earthquake / book / ...), and their content can legitimately contain
    # time-like strings ("remind me ... at 2026-08-16T11:36" in a reminder
    # list) that must NEVER be re-rendered as a provider widget. Without this
    # boundary, a reminder LIST was mangled into "It's 12:27 PM.".
    if details.get("type") not in _KIO_OWNED_TYPES and (
        _PROVIDER_UI_RE.search(message)
        or (_TIME_WIDGET_RE.search(message) and len(message) > 120)
    ):
        cleaned = _sanitize_provider_artifact(message)
        if cleaned and cleaned != message:
            _DIAG["provider_artifact_sanitized"] += 1
            return cleaned
    # BUG 7: a PARTIAL close (primary terminated, background components remain)
    # must be rendered by the structured formatter so the residual note
    # surfaces even though the operator message ("Closed Chrome.") is itself
    # natural — otherwise success and partial would read identically.
    _needs_structured = (
        action in ("close_app", "close")
        and str(details.get("outcome_class") or "").upper() == "SUCCESS_WITH_RESIDUALS"
    )
    # UX RULE (2026-08-10 directive): a successful web-fallback result now
    # carries a short natural message ("Opened Stack Overflow."), so it is
    # treated like any other natural success. Modality stays structured; only
    # failures (or partial closes) route through the structured formatter.
    # An EMPTY message never counts as natural — route it to the formatter
    # which composes a truthful short confirmation.
    if (
        message.strip()
        and _is_natural(message)
        and not _contains_dev_terms(message)
        and not _needs_structured
    ):
        _DIAG["response_already_natural"] += 1
        return message
    formatted = _dispatch_format(action, target, success, details)
    _DIAG["runtime_response_formatted"] += 1
    return formatted


def _dispatch_format(
    action: str, target: str, success: bool, details: Dict[str, Any]
) -> str:
    msg = _ensure_str(details.get("message", ""))
    if action in ("open_app", "open"):
        return format_open_app(target, success, msg, details)
    if action in ("close_app", "close"):
        return format_close_app(target, success, details)
    if action in ("search_web", "search"):
        return format_search(target, success, msg)
    if action == "execute_capability":
        return format_capability(target, success, details)
    if not success:
        # Truthfulness invariant: a failed generic action (close_all_apps,
        # media, etc.) must surface its error — NEVER a success-shaped "Done."
        # which would claim the action completed when it did not.
        return _format_error(msg)
    return format_generic_success(target, msg)


def _format_error(message: str) -> str:
    if not message:
        return "Something went wrong."
    clean = _DEV_PATTERNS.sub("", message).strip()
    clean = re.sub(r'\s+', ' ', clean).strip(".,;: ")
    if not clean:
        return "Something went wrong."
    return clean + "."


_TRIVIAL_FILLERS = frozenset({"ok", "ok.", "done", "done.", "yes", "yes.",
                               "sure", "sure.", "opened", "closed"})


def _is_natural(message: str) -> bool:
    """Heuristic: natural messages don't start with dev verbs."""
    lower = message.lower().strip()
    dev_starts = (
        "routed", "successfully routed", "execution",
        "capability lookup", "search_fallback",
    )
    return not lower.startswith(dev_starts)


def _contains_dev_terms(message: str) -> bool:
    if _DEV_PATTERNS.search(message):
        return True
    if _PID_PATTERN.search(message):
        return True
    return False
