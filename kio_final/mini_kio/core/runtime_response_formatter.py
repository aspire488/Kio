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


def format_open_app(target: str, success: bool, message: str) -> str:
    if not success:
        return _format_error(message)
    display = target.strip().capitalize()
    return f"Opened {display}."


def format_close_app(target: str, success: bool, details: Dict[str, Any]) -> str:
    if not success:
        msg = details.get("message", "")
        if "not running" in msg.lower() or "already closed" in msg.lower() or "was already closed" in msg.lower():
            return f"{target.capitalize()} was already closed."
        if "ambiguous" in msg.lower():
            return f"Couldn't close {target}: multiple matches found."
        if "not found" in msg.lower() or "not track" in msg.lower():
            return f"Couldn't find {target} to close."
        return _format_error(msg)
    if details.get("capability_closed"):
        cap_name = details.get("capability_name", target)
        return f"Closed the {cap_name} session."
    display = target.strip().capitalize()
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
        msg = details.get("message", "")
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


def format_result(
    action: str, target: str, success: bool, details: Dict[str, Any]
) -> str:
    message = details.get("message", "")
    if _is_natural(message) and not _contains_dev_terms(message):
        _DIAG["response_already_natural"] += 1
        return message
    formatted = _dispatch_format(action, target, success, details)
    _DIAG["runtime_response_formatted"] += 1
    return formatted


def _dispatch_format(
    action: str, target: str, success: bool, details: Dict[str, Any]
) -> str:
    if action in ("open_app", "open"):
        return format_open_app(target, success, details.get("message", ""))
    if action in ("close_app", "close"):
        return format_close_app(target, success, details)
    if action in ("search_web", "search"):
        return format_search(target, success, details.get("message", ""))
    if action == "execute_capability":
        return format_capability(target, success, details)
    return format_generic_success(target, details.get("message", ""))


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
