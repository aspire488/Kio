"""CommandRegistry — discoverable dispatch for command patterns."""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

Handler = Callable[..., Optional[dict]]


class CommandRegistry:
    """Ordered list of (name, handler) pairs. First match wins."""

    def __init__(self) -> None:
        self._handlers: list[tuple[str, Handler]] = []

    def register(self, name: str, handler: Handler) -> None:
        self._handlers.append((name, handler))

    def find(self, command: str, lower: str, lower_clean: str) -> Optional[dict]:
        for name, handler in self._handlers:
            try:
                result = handler(command, lower, lower_clean)
                if result is not None:
                    return result
            except Exception:
                logger.exception("Command handler %r failed for %r", name, command)
        return None

    def registered(self) -> list[str]:
        return [n for n, _ in self._handlers]

    def count(self) -> int:
        return len(self._handlers)


_REGISTRY: Optional[CommandRegistry] = None


def get_command_registry() -> CommandRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CommandRegistry()
    return _REGISTRY


def reset_command_registry() -> None:
    global _REGISTRY
    _REGISTRY = None
