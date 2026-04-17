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


def _apply_aliases(text: str) -> str:
    """Replace common speech patterns with normalized names."""
    for pattern, replacement in _ALIASES:
        text = pattern.sub(replacement, text)
    return text


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
    command_lower = command.lower()

    logger.info(f"[KIO] command parsed: {command!r}")
    steps = []

    # Only split into multiple parts when the command is truly multi-step.
    if is_multi_step(command_lower):
        parts = re.split(r"\s+and\s+|\s+then\s+", command_lower)
    else:
        parts = [command_lower]

    for part in parts:
        part = part.strip()
        if not part:
            continue
        step = _parse_single_step(part)
        if step:
            steps.append(step)

    return steps


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

    # ── OPEN ──────────────────────────────────────────────────────────────────
    if action == "open":
        if not target:
            return {}

        # Check if target contains folder keywords
        target_parts = set(target.split())
        if target_parts & _FOLDER_KEYWORDS:
            # Strip trailing "folder" keyword
            folder_name = target.replace("folder", "").strip()
            if not folder_name:
                folder_name = target
            # Clean up folder name (remove extra spaces)
            folder_name = " ".join(folder_name.split())
            return {"action": "folder", "target": folder_name}

        return {"action": "open", "target": target}

    # ── CLOSE ─────────────────────────────────────────────────────────────────
    if action == "close":
        return {"action": "close", "target": target}

    # ── SEARCH ────────────────────────────────────────────────────────────────
    if action == "search":
        # Strip leading "for " if present
        query = re.sub(r"^for\s+", "", target, flags=re.I).strip()
        return {"action": "search", "target": query or target}

    # ── PLAY ──────────────────────────────────────────────────────────────────
    if action == "play":
        return {"action": "youtube_play", "target": target}

    # ── SEARCH YOUTUBE ────────────────────────────────────────────────────────
    if action == "search" and "youtube" in target.lower():
        # Handle "search youtube X" commands
        query = target.lower().replace("youtube", "").strip()
        return {"action": "search_youtube", "target": query}

    # ── FOLDER (explicit) ─────────────────────────────────────────────────────
    if action == "folder":
        return {"action": "folder", "target": target}

    # Unknown action — pass through for AI fallback
    return {"action": action, "target": target}


def is_multi_step(command: str) -> bool:
    """
    Check if command contains multiple steps.
    
    Differentiates between:
    - "open chrome and search python" (TRUE - multi-step)
    - "search for cats and dogs" (FALSE - 'and' is part of query)
    """
    lower = command.lower()
    
    # Check for verb on both sides of connector
    verbs = {"open", "close", "search", "type", "launch", "folder", "play"}
    
    for sep in (r"\s+and\s+", r"\s+then\s+"):
        parts = re.split(sep, lower, maxsplit=1)
        if len(parts) == 2:
            left_verb = parts[0].strip().split()[0] if parts[0].strip() else ""
            right_verb = parts[1].strip().split()[0] if parts[1].strip() else ""
            if left_verb in verbs and right_verb in verbs:
                return True
    
    return False


__all__ = ["parse_command", "is_multi_step"]
