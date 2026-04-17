"""
Personality Engine - Ensures KIO communicates with consistent personality.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PERSONALITY = {
    "assistant_name": "KIO",
    "user_name": "Joel",
    "nicknames": ["Joel", "bro", "dude"],
    "tone": "calm intelligent casual",
    "style": "short helpful responses",
    "persona": "loyal intelligent assistant",
    "humor_level": "light",
    "verbosity": "medium",
}


def get_user_name() -> str:
    """Get the user's name."""
    return PERSONALITY["user_name"]


def get_nicknames() -> list[str]:
    """Get list of user's nicknames."""
    return PERSONALITY["nicknames"]


def generate_response(intent: str, context: dict | None = None) -> str:
    """Generate a personality-appropriate response."""
    user = PERSONALITY["user_name"]

    responses = {
        "ping": f"KIO online and ready, {user}.",
        "system_info": f"System looks good, {user}. Everything running smoothly.",
        "open_target": f"Sure {user}, opening that now.",
        "activate": f"Checking activation, {user}.",
        "memory_usage": f"RAM usage is healthy, {user}.",
        "cpu_usage": f"CPU is at normal levels, {user}.",
        "unknown": f"I can help with that, {user}. What would you like to do?",
    }

    return responses.get(intent, responses["unknown"])


def format_system_message(message: str) -> str:
    """Format system message with personality."""
    return message


def format_greeting() -> str:
    """Generate a friendly greeting."""
    user = PERSONALITY["user_name"]
    tone = PERSONALITY["tone"]

    if "casual" in tone:
        return f"Hey {user}! KIO here, ready to help."
    else:
        return f"Hello {user}. KIO is online."


def format_farewell() -> str:
    """Generate a friendly farewell."""
    user = PERSONALITY["user_name"]
    return f"Later {user}. KIO will be here when you get back."


def format_proactive_message(message: str, user_name: str | None = None) -> str:
    """Format a proactive message."""
    if user_name is None:
        user_name = PERSONALITY["user_name"]
    return f"{user_name}, {message}"


__all__ = [
    "PERSONALITY",
    "get_user_name",
    "get_nicknames",
    "generate_response",
    "format_system_message",
    "format_greeting",
    "format_farewell",
    "format_proactive_message",
]
