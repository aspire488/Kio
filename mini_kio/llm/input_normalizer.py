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

from mini_kio.llm.emoji_normalizer import normalize_emoji_text

logger = logging.getLogger(__name__)

_TYPO_MAP = {
    "pythn": "python",
    "recusrion": "recursion",
    "machien": "machine",
    "baiscs": "basics",
    "sytnax": "syntax",
    "javascrpt": "javascript",
    # Small generic abbreviation/contracton lexicon (language-level)
    "u": "you",
    "ur": "your",
    "r": "are",
    "rn": "right now",
    "tmrw": "tomorrow",
    "tdy": "today",
    "pls": "please",
    "ty": "thank you",
    "thx": "thanks",
    "im": "i am",
    "idk": "i do not know",
    "whats": "what is",
    "whos": "who is",
    "hows": "how is",
}
# Generic fuzzy vocabulary for typo recovery (constrained, not whole language)
# Covers: resource keywords, common query targets, general conversational words
# The fuzzy matcher only corrects tokens >= 4 chars with difflib >= 0.85 cutoff
#
# IMPORTANT: entries here must NOT be close to common English words.
# e.g. 'storage' matches 'strange' (0.857 ratio), 'burning' matches 'bring'
# (0.833 ratio) — these corrupted "Doctor Strange bring back" into
# "Doctor storage burning back". Only include words where the user is
# genuinely likely to MISSPELL them, not words that are themselves close
# to valid English.
_FUZZY_VOCAB = frozenset({
    # Core query words
    "what", "who", "how", "when", "where", "why",
    # Conversational
    "hello", "thanks", "please", "about", "because",
    "tomorrow", "today", "right", "now",
    # Pronouns / contractions
    "you", "your", "are",
    # Resource keywords — ONLY words unlikely to collide with common English
    "python", "battery", "cpu",
    "projects", "status", "health", "uptime", "capabilities",
    # Common query verbs
    "working", "building", "running", "using", "doing",
    # Technical
    "terminal", "browser", "telegram", "session", "process",
})

_CONTINUITY_TRIGGERS = {"next", "continue", "more"}

class InputNormalizer:
    """Deterministic input normalization and routing bypass."""

    def __init__(self):
        self._diag = {
            "sanitize_applied": False,
            "typo_normalization_applied": False,
            "authority_override_used": False,
            "continuity_resume_used": False,
            "emoji_normalize_applied": False,
            "emoji_sanitize_applied": False,
        }

    def reset_diag(self):
        self._diag = {
            "sanitize_applied": False,
            "typo_normalization_applied": False,
            "authority_override_used": False,
            "continuity_resume_used": False,
            "emoji_normalize_applied": False,
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

        # 1b. Emoji normalization — replace mapped emojis with semantic tags
        # BEFORE non-ASCII stripping. Unmapped emojis still get stripped below.
        emoji_normalized = normalize_emoji_text(text)
        if emoji_normalized != text:
            self._diag["emoji_normalize_applied"] = True
        text = emoji_normalized

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
        """Fix typos via small deterministic map + bounded fuzzy vocabulary."""
        applied = False
        sorted_typos = sorted(_TYPO_MAP.keys(), key=len, reverse=True)
        working_text = " " + text + " "
        for typo in sorted_typos:
            correction = _TYPO_MAP[typo]
            pattern = r'\b' + re.escape(typo) + r'\b'
            if re.search(pattern, working_text):
                working_text = re.sub(pattern, correction, working_text)
                applied = True
        # Bounded fuzzy recovery for remaining single-token typos (e.g. burnin->burning, memroy->memory)
        # Only against _FUZZY_VOCAB, only for tokens >=4 chars, only high-confidence difflib >=0.8
        import difflib
        toks = working_text.split()
        out_toks = []
        for tok in toks:
            core = tok.strip(".,!?;:'\"()")
            low = core.lower()
            if low in _TYPO_MAP or low in _FUZZY_VOCAB or len(low) < 4:
                out_toks.append(tok)
                continue
            # Preserve URLs, code, filenames, quoted text
            if "/" in tok or "." in tok and len(tok) > 6:
                out_toks.append(tok)
                continue
            cand = difflib.get_close_matches(low, _FUZZY_VOCAB, n=1, cutoff=0.85)
            if cand and cand[0] != low:
                # Preserve original casing/punctuation
                out_toks.append(tok.replace(core, cand[0]))
                applied = True
            else:
                out_toks.append(tok)
        working_text = " ".join(out_toks)
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
