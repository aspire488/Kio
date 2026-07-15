import re
import random
from typing import Optional
from mini_kio.resolvers.base import BaseResolver
from mini_kio.llm.session_state import SessionState
from mini_kio.llm.trace_context import TraceContext
from mini_kio.llm.identity_dataset import resolve as identity_resolve
from mini_kio.llm.conversation_models import ConversationTone

_GREETING_QUALIFIERS = frozenset({
    "kio", "bro", "dude", "buddy", "mate", "man", "there",
})

_GREETING_CATEGORY: dict[str, str] = {
    "hello": "hello", "hi": "hello", "hey": "hello", "yo": "hello",
    "wassup": "hello", "what's up": "hello", "whats up": "hello", "what is up": "hello",
    "good morning": "hello", "good afternoon": "hello", "good evening": "hello",
    "how are you": "how_are_you", "how are you doing": "how_are_you",
    "bye": "farewell", "goodbye": "farewell",
    "thanks": "thanks", "thank you": "thanks", "appreciate it": "thanks", "that helped": "thanks",
    "okay": "okay", "ok": "okay",
    "cool": "positive", "nice": "positive", "good": "positive",
    "ping": "ping", "help": "help",
}

_GREETING_VARIANTS: dict[str, list[str]] = {
    "hello": ["Hello.", "Hi there.", "I'm here.", "Hey."],
    "how_are_you": ["Operational.", "Running.", "System nominal."],
    "thanks": ["You're welcome.", "No problem.", "Happy to help.", "Anytime."],
    "farewell": ["See you later.", "Goodbye.", "Catch you later.", "Later."],
    "okay": ["Ok.", "Got it.", "Heard."],
    "ping": ["I'm here.", "KIO present.", "Present.", "Here."],
    "help": ["I can open apps, search the web, and play media."],
}

_JOKE_TRIGGERS = frozenset({"joke", "joke around", "can you joke", "tell me a joke"})
_JOKE_VARIANTS = [
    "Why don't scientists trust atoms? Because they make up everything.",
    "What do you call a fake noodle? An impasta.",
    "Why did the developer go broke? Because he used up all his cache.",
]

class IdentityResolver(BaseResolver):
    """Handles identity queries, greetings, and jokes."""
    
    def resolve(self, text: str, state: SessionState, trace: TraceContext) -> Optional[str]:
        text_clean = text.lower().strip().strip(".,!?;:")
        text_clean = text_clean.replace("who're you", "who are you")
        text_clean = text_clean.replace("who're u", "who are you")
        text_clean = text_clean.replace("who r u", "who are you")
        text_clean = text_clean.replace("whos kio", "who's kio")
        text_clean = text_clean.replace("whats kio", "what's kio")
        
        # 1. Canonical Identity Match
        id_match = identity_resolve(text_clean)
        if id_match:
            trace.add_step("IdentityResolver: canonical identity match")
            return id_match[0]
            
        # 2. Jokes
        if any(trigger in text_clean for trigger in _JOKE_TRIGGERS):
            trace.add_step("IdentityResolver: joke triggered")
            idx = state.rotation_counters.get("joke", 0) % len(_JOKE_VARIANTS)
            state.rotation_counters["joke"] = idx + 1
            return _JOKE_VARIANTS[idx]
            
        # 3. Greetings
        # Strip qualifiers
        words = text_clean.split()
        stripped = " ".join([w for w in words if w not in _GREETING_QUALIFIERS])
        
        category = _GREETING_CATEGORY.get(stripped) or _GREETING_CATEGORY.get(text_clean)
        if category:
            trace.add_step(f"IdentityResolver: greeting category '{category}'")
            variants = _GREETING_VARIANTS.get(category, ["Ok."])
            idx = state.rotation_counters.get(category, 0) % len(variants)
            state.rotation_counters[category] = idx + 1
            return variants[idx]

        return None
