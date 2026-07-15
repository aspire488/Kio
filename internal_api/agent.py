"""Agent runtime protocol for internal API.

Abstracts lifecycle management for autonomous agents.
"""

from __future__ import annotations
from typing import Protocol, Any, Mapping


class AgentRuntime(Protocol):
    """Interface for creating, running, and terminating agents."""

    def start(self, agent_id: str, config: Mapping[str, Any] | None = None) -> Any: ...
    """Start an agent identified by *agent_id* with optional *config*; returns a handle."""

    def stop(self, handle: Any) -> None: ...
    """Stop the running agent associated with *handle*."""

    def send_message(self, handle: Any, message: Any) -> None: ...
    """Deliver a *message* to the agent referenced by *handle*."""
