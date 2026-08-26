"""
phrases.py — Canonical Phrase Sets
===================================
Single source of truth for shared conversational vocabulary.

These frozensets are imported by:
  - pipeline/_IntentClassifier (primary routing)
  - llm/intent_classifier.py (secondary classification)
  - Other subsystems that need canonical phrase membership

Architecture rule: ONE canonical owner per semantic concept.
Adding a greeting phrase here automatically makes it recognized
by ALL subsystems that import this module.
"""

from __future__ import annotations

# ── Greetings ────────────────────────────────────────────────────────────────
# Canonical greeting phrases. Recognized by pipeline routing AND
# LLM intent classifier. New greetings go HERE, not in individual files.

GREETINGS = frozenset({
    "hello", "hi", "hey", "yo", "hola", "sup", "wassup", "what's up", "whats up",
    "good morning", "good afternoon", "good evening", "heyy", "bro", "broo",
    # "what's good" is the same greeting idiom as "what's up" — never a
    # question about the word "good" (live: "yo whats good" was stripped
    # to "what is good" and answered with a definition of "good").
    "what's good", "whats good", "wassup good", "waddup", "sup bro", "yo bro",
    "wsg", "wyd", "rn",
})

# ── Acknowledgements ─────────────────────────────────────────────────────────
# Responses that acknowledge receipt without adding new information.

ACKNOWLEDGEMENTS = frozenset({
    "i see", "oh i see", "ah i see", "i understand", "got it", "makes sense",
    "right", "alright", "cool", "nice", "good", "understood", "that makes sense",
})

# ── Thanks ───────────────────────────────────────────────────────────────────
# Gratitude expressions.

THANKS = frozenset({"thanks", "thank you", "thankyou", "ty", "thx"})

# ── Farewells ────────────────────────────────────────────────────────────────
# Parting expressions.

FAREWELLS = frozenset({"bye", "goodbye", "see you", "later", "goodnight", "gn"})

# ── Confirmations ────────────────────────────────────────────────────────────
# Affirmative responses that accept a proposal or confirm understanding.

CONFIRMATIONS = frozenset({
    "yes", "yeah", "yea", "yep", "yup", "yess", "sure", "ok", "okay",
    "go ahead", "do it", "start it", "play it", "yes start it",
    "yes play it", "yes do it", "sounds good", "let's go", "let's do it",
})

# ── Rejections ───────────────────────────────────────────────────────────────
# Negative responses that decline or request alternatives.

REJECTIONS = frozenset({
    "no", "nope", "nah", "nahh", "naah", "noo", "not this", "not that",
    "something else", "another one", "try another", "try something different",
    "next", "skip", "change it", "different",
})

# ── Media Transport ──────────────────────────────────────────────────────────
# Canonical media transport commands. Used by pipeline for initial
# classification. Media manager has its own follow-up detection
# (legitimate separation: initial intent vs. follow-up state handling).

MEDIA_TRANSPORT = frozenset({
    "pause", "resume", "stop", "mute", "unmute",
    "next", "next video", "next track", "skip", "skip video",
    "previous", "prev", "previous video", "previous track", "go back",
    "volume up", "increase volume", "turn it up", "louder",
    "volume down", "decrease volume", "turn it down", "quieter", "lower volume",
    "continue", "keep going", "continue playing",
    "carry on", "keep playing", "resume it",
})

# ── System Actions ───────────────────────────────────────────────────────────
# Deterministic system commands.

SYSTEM_ACTIONS = frozenset({"shutdown", "restart", "lock", "unlock", "recovery", "recover"})

# ── Folder Keywords ──────────────────────────────────────────────────────────
# Recognized folder names for "open downloads folder" style commands.

FOLDER_KEYWORDS = frozenset({
    "downloads", "desktop", "documents", "pictures", "music", "videos",
    "home", "appdata", "kio",
})

# ── Forbidden Targets ────────────────────────────────────────────────────────
# Safety boundary: these system targets must never be opened/killed by KIO.

FORBIDDEN_TARGETS = frozenset({
    "cmd", "powershell", "regedit", "taskmgr", "msconfig", "control.exe",
    "explorer", "terminal", "services",
})
