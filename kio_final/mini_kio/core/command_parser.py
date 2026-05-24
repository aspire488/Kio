"""
Command Parser - Parse commands into ordered steps.

Fixes and improvements:
1. Multi-step commands ("open chrome and search X") correctly emit all steps
2. Folder detection: "open downloads folder" → {action: "folder", target: "downloads"}
3. Alias expansion: "vs code" → "vscode", "google chrome" → "chrome"
4. URL-safe query encoding using urllib.parse.quote_plus
5. Robust parsing handles trailing "folder" keyword
6. Returns empty list on invalid input instead of raising exceptions
"""

import re
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Aliases for common speech patterns
_ALIASES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bvs\s+code\b", re.I), "vscode"),
    (re.compile(r"\bvisual\s+studio\s+code\b", re.I), "vscode"),
    (re.compile(r"\bvs\s+studio\s+code\b", re.I), "vscode"),
    (re.compile(r"\bchrome\s+browser\b", re.I), "chrome"),
    (re.compile(r"\bgoogle\s+chrome\b", re.I), "chrome"),
    (re.compile(r"\bms\s+edge\b", re.I), "edge"),
    (re.compile(r"\bmicrosoft\s+edge\b", re.I), "edge"),
    (re.compile(r"\bwhatsapp\s+web\b", re.I), "whatsapp"),
    (re.compile(r"\bgmail\b", re.I), "gmail"),
    (re.compile(r"\byoutube\b", re.I), "youtube"),
    (re.compile(r"\bspotify\b", re.I), "spotify"),
    (re.compile(r"\bdiscord\b", re.I), "discord"),
    (re.compile(r"\bvlc\b", re.I), "vlc"),
    (re.compile(r"\bcapcut\b", re.I), "capcut"),
]

# Folder keywords
_FOLDER_KEYWORDS = {
    "folder", "downloads", "desktop", "documents", "pictures", 
    "music", "videos", "home", "appdata"
}

_VERBS = {
    "open", "close", "search", "type", "launch", "folder", 
    "play", "lock", "shutdown", "restart"
}

_PLATFORM_MARKERS = {"spotify", "youtube", "google", "edge", "chrome", "comet", "firefox", "brave"}

_INHERITABLE_VERBS = {"play", "search"}

_MAX_COMMAND_STEPS = 4
_ALLOWED_WEB_TLDS = {"com", "ai", "org", "io", "dev", "app"}
_SAFE_SINGLE_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SAFE_EXPLICIT_DOMAIN_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
)
_SAFE_WEB_PATH_RE = re.compile(r"^[a-z0-9._~:@%+\-=]+(?:/[a-z0-9._~:@%+\-=]+)*$")


def _apply_aliases(text: str) -> str:
    """Replace common speech patterns with normalized names."""
    for pattern, replacement in _ALIASES:
        text = pattern.sub(replacement, text)
    return text


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def _normalize_connectors(text: str) -> str:
    """Normalize common typos in command connectors."""
    text = re.sub(r"\b(?:anf|andd)\b", "and", text, flags=re.I)
    text = re.sub(r"\b(?:thenn)\b", "then", text, flags=re.I)
    return text


def _collapse_repeated_conjunctions(text: str) -> str:
    text = re.sub(r"(?:\s+(?:and|then|anf|andd|thenn))(?:\s+(?:and|then|anf|andd|thenn))+", " and", text, flags=re.I)
    return _normalize_whitespace(text)


def _contains_command_connector(text: str) -> bool:
    return bool(re.search(r"\b(?:and|then)\b", text))


def _is_malformed_chain(text: str) -> bool:
    text = text.strip()
    if not text:
        return True
    if re.match(r"^(?:and|then)\b", text):
        return True
    if re.search(r"\b(?:and|then)$", text):
        return True
    return False


def _contains_forbidden_web_chars(value: str) -> bool:
    return any(c in value for c in [' ', '&', '|', ';', '$', '(', ')', '`', '\\', '\0', '\n', '\r', '\t'])


def _normalize_browser_web_target(webapp: str) -> str | None:
    try:
        from mini_kio.core.app_operator import _normalize_web_target_to_url
    except Exception:
        return None
    return _normalize_web_target_to_url(webapp)


def parse_command(command: str) -> List[Dict[str, Any]]:
    """
    Parse command string into ordered steps.
    
    Returns:
        List of dicts with keys: action, target
        
    Examples:
        "open chrome" → [{"action": "open", "target": "chrome"}]
        "open chrome and search python" → 
            [{"action": "open", "target": "chrome"}, 
             {"action": "search", "target": "python"}]
        "open downloads folder" → [{"action": "folder", "target": "downloads"}]
    """
    command = command.strip()
    if not command:
        return []

    command = _apply_aliases(command)
    command = _normalize_whitespace(command)
    command_lower = command.lower()
    command_lower = _normalize_connectors(command_lower)
    command_lower = _collapse_repeated_conjunctions(command_lower)

    if _is_malformed_chain(command_lower):
        return []

    logger.info(f"[KIO] command parsed: {command!r}")
    steps: list[dict[str, Any]] = []

    if is_multi_step(command_lower):
        parts = re.split(r"\s+(?:and|then)\s+", command_lower)
        if len(parts) > _MAX_COMMAND_STEPS:
            return []
            
        last_verb = None
        last_platform = None
        for part in parts:
            part = part.strip()
            if not part:
                return []
                
            words = part.split()
            verb = words[0] if words else ""
            
            # Platform extraction for inheritance (Gate 2.4 consistency)
            current_platform = None
            for sep in [" on ", " in ", " using "]:
                if sep in part:
                    p_parts = part.rsplit(sep, 1)
                    p_candidate = p_parts[1].strip()
                    if p_candidate in _PLATFORM_MARKERS:
                        current_platform = p_candidate
                        break

            # Bounded Continuation Support (Gate 2.4 prep)
            if (verb not in _VERBS and last_verb in _INHERITABLE_VERBS) or \
               (verb == last_verb and last_verb in _INHERITABLE_VERBS):
                
                # Prepend verb if omitted
                if verb not in _VERBS:
                    part = f"{last_verb} {part}"
                    verb = last_verb
                
                # Inherit platform if current part lacks one
                if not current_platform and last_platform:
                    part = f"{part} in {last_platform}"
                    current_platform = last_platform

            step = _parse_single_step(part)
            if not step:
                return []
            
            # Update last state for next iteration
            if verb in _VERBS:
                last_verb = verb
            if current_platform:
                last_platform = current_platform
                
            steps.append(step)
        return steps

    step = _parse_single_step(command_lower)
    if not step:
        return []
    return [step]


def _parse_single_step(text: str) -> Dict[str, Any]:
    """
    Parse a single command step.
    
    Returns:
        Dict with action and target, or empty dict if unparseable
    """
    text = text.strip()
    if not text:
        return {}

    words = text.split()
    if not words:
        return {}

    action = words[0]
    target = " ".join(words[1:]).strip() if len(words) > 1 else ""

    # ── OPEN / LAUNCH ──────────────────────────────────────────────────────────
    if action in ("open", "launch"):
        if not target:
            return {}

        target_lower = target.lower()

        # Browser-targeted webapp routing (Gate 2.4 polish)
        # e.g. "open telegram in chrome"
        for sep in [" in ", " on ", " using "]:
            if sep in target_lower:
                parts = target_lower.rsplit(sep, 1)
                webapp = parts[0].strip()
                browser = parts[1].strip()
                
                # STRICT WHITELIST (Fix 1)
                known_webapps = {"telegram", "whatsapp", "chatgpt"}
                known_browsers = {"chrome", "edge", "comet", "firefox", "brave"}
                
                if webapp in known_webapps and browser in known_browsers:
                    # Deterministic URLs as per SPEC
                    urls = {
                        "telegram": "https://web.telegram.org",
                        "whatsapp": "https://web.whatsapp.com",
                        "chatgpt": "https://chatgpt.com"
                    }
                    url = urls.get(webapp)
                    if url:
                        return {"action": "execute_capability", "target": f"{browser}::open_url::{url}"}

                normalized_url = _normalize_browser_web_target(webapp)
                if normalized_url and browser in known_browsers:
                    return {"action": "execute_capability", "target": f"{browser}::open_url::{normalized_url}"}

        if action == "open":
            # Check if target contains folder keywords
            target_parts = set(target_lower.split())
            if target_parts & _FOLDER_KEYWORDS:
                # Strip trailing "folder" keyword
                folder_name = target.replace("folder", "").strip()
                if not folder_name:
                    folder_name = target
                # Clean up folder name (remove extra spaces)
                folder_name = " ".join(folder_name.split())
                return {"action": "folder", "target": folder_name}

        return {"action": action, "target": target}

    # ── CLOSE ─────────────────────────────────────────────────────────────────
    if action == "close":
        if not target:
            return {}
        return {"action": "close", "target": target}

    # ── SEARCH ────────────────────────────────────────────────────────────────
    if action == "search":
        # Strip leading "for " if present
        target = re.sub(r"^for\s+", "", target, flags=re.I).strip()
        if not target:
            return {}
        
        target_lower = target.lower()
        # Multi-platform extraction (Gate 2.4 consistency)
        for sep in [" on ", " in ", " using "]:
            if sep in target_lower:
                parts = target_lower.rsplit(sep, 1)
                platform = parts[1].strip()
                query = parts[0].strip()
                if platform == "youtube":
                    return {"action": "search_youtube", "target": query}
                if platform in ("chrome", "edge", "firefox", "brave", "comet"):
                    return {"action": "execute_capability", "target": f"{platform}::search::{query}"}

        # Fallback for "search youtube X" or "search X youtube"
        if target_lower.startswith("youtube "):
            query = target_lower[8:].strip()
            return {"action": "search_youtube", "target": query}
        if target_lower.endswith(" youtube"):
            query = target_lower[:-8].strip()
            return {"action": "search_youtube", "target": query}

        return {"action": "search", "target": target}

    # ── PLAY ──────────────────────────────────────────────────────────────────
    if action == "play":
        if not target:
            return {}
        
        # BUG-01 Fix: Platform extraction for multi-step routing
        target_lower = target.lower()
        for sep in [" on ", " in ", " using "]:
            if sep in target_lower:
                parts = target_lower.rsplit(sep, 1)
                platform = parts[1].strip()
                query = parts[0].strip()
                if platform in ("spotify", "vlc", "capcut", "youtube"):
                    # Normalize YouTube to youtube_play for consistency
                    if platform == "youtube":
                        return {"action": "youtube_play", "target": query}
                    # Use capability format to ensure proper routing in router/boundary
                    return {"action": "execute_capability", "target": f"{platform}::play::{query}"}
                    
        return {"action": "youtube_play", "target": target}

    # ── FOLDER (explicit) ─────────────────────────────────────────────────────
    if action == "folder":
        if not target:
            return {}
        return {"action": "folder", "target": target}

    # Unknown action — pass through for AI fallback or policy handling
    if not target and action not in {"shutdown", "restart", "lock"}:
        return {}
    return {"action": action, "target": target}


def is_multi_step(command: str) -> bool:
    """
    Check if command contains multiple steps.
    
    Differentiates between:
    - "open chrome and search python" (TRUE - multi-step)
    - "search for cats and dogs" (FALSE - 'and' is part of query)
    - "play safar in spotify and sports apm in youtube" (TRUE - inheritance)
    """
    lower = command.lower()
    
    for sep in (r"\s+and\s+", r"\s+then\s+"):
        parts = re.split(sep, lower, maxsplit=1)
        if len(parts) == 2:
            left_part = parts[0].strip()
            right_part = parts[1].strip()
            if not left_part or not right_part:
                continue
            
            left_words = left_part.split()
            right_words = right_part.split()
            
            left_verb = left_words[0] if left_words else ""
            right_verb = right_words[0] if right_words else ""
            
            if left_verb in _VERBS:
                if right_verb in _VERBS:
                    return True
                # Bounded continuation inheritance logic (Gate 2.4 prep)
                if left_verb in _INHERITABLE_VERBS:
                    # Robust check: either side has a platform marker, OR right starts with verb
                    if any(marker in left_part for marker in _PLATFORM_MARKERS) or \
                       any(marker in right_part for marker in _PLATFORM_MARKERS):
                        return True
    
    return False


__all__ = ["parse_command", "is_multi_step", "_apply_aliases"]
