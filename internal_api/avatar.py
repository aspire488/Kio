"""Avatar runtime protocol for internal API.

Defines abstract operations for rendering or managing avatars.
"""

from __future__ import annotations
from typing import Protocol, Any


class AvatarRuntime(Protocol):
    """Interface for avatar display and interaction."""

    def render(self, state: Any) -> None: ...
    """Render the avatar based on *state* (e.g., facial expression, pose)."""

    def update(self, data: Any) -> None: ...
    """Update internal avatar state with *data* (e.g., emotions, gestures)."""
