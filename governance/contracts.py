'''Governance contract protocols.'''

from __future__ import annotations
from typing import Protocol, runtime_checkable

@runtime_checkable
class CapabilityContract(Protocol):
    """Interface for capability contract validation and enumeration."""

    def validate(self, capability: object) -> None:
        """Validate that *capability* conforms to required schema.

        Should raise if validation fails.
        """
        ...

    def supports(self, capability: object) -> bool:
        """Return ``True`` if the contract supports the given *capability*."""
        ...

    def list_capabilities(self) -> list[object]:
        """Return a collection of all capabilities known to the contract."""
        ...

@runtime_checkable
class PermissionValidator(Protocol):
    """Interface for permission validation and authorization."""

    def validate(self, permission: object) -> None:
        """Validate a *permission* object, raising on error."""
        ...

    def authorize(self, resource: str, action: str) -> bool:
        """Return ``True`` if *action* on *resource* is permitted."""
        ...

    def list_permissions(self) -> list[object]:
        """Return all known permission objects."""
        ...
