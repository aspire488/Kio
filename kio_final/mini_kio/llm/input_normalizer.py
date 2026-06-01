"""
input_normalizer.py — Gate 5 Final Stabilization Input Pipeline

Responsible for:
- early sanitization (noise/emoji removal)
- typo normalization (pythn -> python)
- deterministic authority overrides (identity bypass)
- continuity-first routing (next/continue/more)
"""

import re
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

_TYPO_MAP = {
    "pythn baiscs": "python basics",
    "pythn": "python",
    "recusrion": "recursion",
    "machien learning": "machine learning",
    "machien": "machine",
    "python sytnax": "python syntax",
    "baiscs": "basics",
    "sytnax": "syntax",
    "whos": "who is",
    "ur": "your",
    "u": "you",
    "r": "are",
    "wat": "what",
    "wot": "what",
    "helo": "hello",
    "hellp": "hello",
    "thx": "thanks",
    "thanx": "thanks",
    "javascrpt": "javascript",
}

_CONTINUITY_TRIGGERS = {"next", "continue", "more"}

class InputNormalizer:
    """Deterministic input normalization and routing bypass."""

    def __init__(self):
        self._diag = {
            "sanitize_applied": False,
            "typo_normalization_applied": False,
            "authority_override_used": False,
            "continuity_resume_used": False,
            "emoji_sanitize_applied": False,
        }

    def reset_diag(self):
        self._diag = {
            "sanitize_applied": False,
            "typo_normalization_applied": False,
            "authority_override_used": False,
            "continuity_resume_used": False,
            "emoji_sanitize_applied": False,
        }

    def get_diag(self) -> Dict[str, bool]:
        return dict(self._diag)

    @staticmethod
    def strip_emoji(text: str) -> str:
        """Strip emoji and non-ASCII noise characters from input."""
        if not text:
            return ""
        return re.sub(r'[^\x00-\x7F]+', ' ', text).strip()

    def sanitize(self, text: str) -> str:
        """Strip noise, emojis, and normalize punctuation while preserving URLs and command targets."""
        if not text:
            return ""
        
        original = text
        
        # 1. Detect and preserve URLs
        urls = re.findall(r'https?://\S+', text)
        for i, url in enumerate(urls):
            text = text.replace(url, f"__URL_PLACEHOLDER_{i}__")
            
        # 2. Strip emojis and symbol noise (preserving basic alphanumeric and command punctuation)
        # We want to keep: a-z A-Z 0-9 space . , ! ? : ; / - _ ( ) [ ] { } ' " 
        # and our placeholders
        text = re.sub(r'[^\x00-\x7F]+', ' ', text)
        
        # More aggressive emoji/symbol strip if still non-ASCII after first pass
        # Use a regex that allows basic ASCII but strips high-range symbols
        text = re.sub(r'[^\w\s\.,!\?\:;/\-_\(\)\[\]\{\}\'"\+=@#\$%\^&\*~`|]', ' ', text)
        
        # 3. Restore URLs
        for i, url in enumerate(urls):
            text = text.replace(f"__URL_PLACEHOLDER_{i}__", url)
            
        # 4. Normalize punctuation
        text = text.replace("’", "'").replace("‘", "'")
        text = re.sub(r'([\.!\?])\1+', r'\1', text)
        
        # 5. Lowercase safely
        text = text.lower().strip()
        
        if text != original.lower().strip():
            self._diag["sanitize_applied"] = True
            # Check specifically for emoji/noise removal
            clean_original = re.sub(r'[^\x00-\x7F]+', ' ', original.lower().strip())
            if clean_original != original.lower().strip():
                 self._diag["emoji_sanitize_applied"] = True
            
        return text

    def normalize_typos(self, text: str) -> str:
        """Fix common typos based on deterministic map."""
        # Multi-word/compound typos first (e.g. "pythn baiscs")
        applied = False
        
        # Sort keys by length descending to catch longest matches first
        sorted_typos = sorted(_TYPO_MAP.keys(), key=len, reverse=True)
        
        working_text = " " + text + " "
        for typo in sorted_typos:
            correction = _TYPO_MAP[typo]
            # Match with word boundaries
            pattern = r'\b' + re.escape(typo) + r'\b'
            if re.search(pattern, working_text):
                working_text = re.sub(pattern, correction, working_text)
                applied = True
        
        text = working_text.strip()
                
        if applied:
            self._diag["typo_normalization_applied"] = True
            
        return text

    def check_authority_override(self, text: str) -> Optional[str]:
        """Check for deterministic authority bypasses.
        
        Deprecated — identity queries are handled centrally by identity_dataset.
        Retained as no-op for backward compatibility.
        """
        return None

    def is_continuity_request(self, text: str) -> bool:
        """Check if the input is a continuation trigger."""
        clean = text.strip(".,!?;: ")
        if clean in _CONTINUITY_TRIGGERS:
            # We don't set diag here yet, only if it's actually used with an active lesson
            return True
        return False

    def mark_continuity_used(self):
        self._diag["continuity_resume_used"] = True
