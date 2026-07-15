"""Execution fabric protocol for internal API.

Defines abstract task execution capabilities required by the KIO Executive.
"""

from __future__ import annotations
from typing import Protocol, Any, Mapping


class ExecutionEngine(Protocol):
    """Abstract interface for scheduling and running tasks."""

    def submit(self, task: Any, *, metadata: Mapping[str, Any] | None = None) -> Any: ...
    """Submit a *task* for execution, optionally with *metadata*; returns a handle or result."""

    def cancel(self, handle: Any) -> None: ...
    """Attempt to cancel a previously submitted task identified by *handle*."""
