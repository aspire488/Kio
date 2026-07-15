"""Voice runtime protocol for internal API.

Abstracts audio input/output operations used by KIO.
"""

from __future__ import annotations
from typing import Protocol, Any


class VoiceRuntime(Protocol):
    """Interface for handling voice input and output."""

    def listen(self) -> Any: ...
    """Capture audio from the microphone and return a representation (e.g., text)."""

    def speak(self, content: str) -> None: ...
    """Synthesize *content* to audio output.

    ponytail: uses simple TTS; replace with high‑quality model if latency matters.
    """
