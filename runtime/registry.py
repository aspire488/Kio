"""Runtime registry interfaces.

Provides a minimal contract for registering and retrieving runtime components.
"""

from __future__ import annotations

import abc
from typing import Protocol, runtime_checkable, Any, TypeVar, Generic

T = TypeVar("T")

@runtime_checkable
class RuntimeRegistry(Protocol):
    """Interface for a component registry.

    Implementations must support generic registration and lookup.
    """

    def register(self, name: str, component: Any) -> None:
        """Register a component under *name*."""
        ...

    def get(self, name: str) -> Any:
        """Retrieve a registered component by *name*; raises ``KeyError`` if missing."""
        ...

    def unregister(self, name: str) -> None:
        """Remove a component from the registry."""
        ...

# ponytail: Generic typing omitted for simplicity; concrete registries can be more specific.
