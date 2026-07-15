"""Runtime event protocol.

Defines the shape of events emitted within the runtime system.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable, Any, Mapping

@runtime_checkable
class RuntimeEvent(Protocol):
    """Interface for runtime events.

    Concrete events should expose a ``type`` identifier and an optional payload.
    """

    @property
    def type(self) -> str:
        ...

    @property
    def payload(self) -> Mapping[str, Any] | None:
        ...

# ponytail: Simple mapping payload; more structured event data can subclass this.
