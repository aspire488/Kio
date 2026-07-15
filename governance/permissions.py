'''Governance permission abstractions.'''

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

class PermissionLevel(Enum):
    """Permission granularity levels."""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"

@dataclass(frozen=True)
class Permission:
    """Permission granted for a specific resource."""
    resource: str
    """Resource identifier the permission applies to."""
    level: PermissionLevel
    """Level of access."""
    metadata: Mapping[str, Any] | None = None
    """Optional extra data."""
