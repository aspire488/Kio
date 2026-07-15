'''Governance capability abstractions.'''

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

class CapabilityType(Enum):
    """Enumerates possible capability categories."""
    SYSTEM = "system"
    BROWSER = "browser"
    FILESYSTEM = "filesystem"
    TERMINAL = "terminal"
    DESKTOP = "desktop"
    WORKFLOW = "workflow"
    NETWORK = "network"
    COMMUNICATION = "communication"
    VOICE = "voice"
    AVATAR = "avatar"
    AGENT = "agent"
    CUSTOM = "custom"

@dataclass(frozen=True)
class Capability:
    """Definition of a capability offered by a provider."""
    id: str
    """Unique identifier for the capability."""
    name: str
    """Human‑readable name."""
    category: CapabilityType
    """Capability type/category."""
    description: str | None = None
    """Optional free‑form description."""
    metadata: Mapping[str, Any] | None = None
    """Arbitrary additional data supplied by the provider."""
