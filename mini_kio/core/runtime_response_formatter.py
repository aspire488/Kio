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
}
_DEV_PATTERNS = re.compile(
    r'\b(Routed|search_fallback|capability lookup|execution classification|'
    r'outcome_class|verification_status|failure_class|'
    r'execute_capability|execution_id|tool_version|handler)\b',
    re.IGNORECASE,
)
_PID_PATTERN = re.compile(r'\s*\(pid \d+\)')
_BROWSER_NAME_OVERRIDES = {"chrome": "Chrome", "edge": "Edge", "firefox": "Firefox", "brave": "Brave", "comet": "Comet", "opera": "Opera"}


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


def format_open_app(target: str, success: bool, message: str) -> str:
    if not success:
        return _format_error(_ensure_str(message))
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


def format_result(
    action: str, target: str, success: bool, details: Dict[str, Any]
) -> str:
    message = _ensure_str(details.get("message", ""))
    # BUG 7: a PARTIAL close (primary terminated, background components remain)
    # must be rendered by the structured formatter so the residual note
    # surfaces even though the operator message ("Closed Chrome.") is itself
    # natural — otherwise success and partial would read identically.
    _needs_structured = (
        action in ("close_app", "close")
        and str(details.get("outcome_class") or "").upper() == "SUCCESS_WITH_RESIDUALS"
    )
    if _is_natural(message) and not _contains_dev_terms(message) and not _needs_structured:
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
        return format_open_app(target, success, msg)
    if action in ("close_app", "close"):
        return format_close_app(target, success, details)
    if action in ("search_web", "search"):
        return format_search(target, success, msg)
    if action == "execute_capability":
        return format_capability(target, success, details)
    return format_generic_success(target, msg)


def _format_error(message: str) -> str:
    if not message:
        return "Something went wrong."
    clean = _DEV_PATTERNS.sub("", message).strip()
    clean = re.sub(r'\s+', ' ', clean).strip(".,;: ")
    if not clean:
        return "Something went wrong."
    return clean + "."


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
