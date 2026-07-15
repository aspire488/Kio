from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Mapping, Any


class ProviderState(enum.Enum):
    """Lifecycle states a provider can be in."""

    INITIALIZING = enum.auto()
    READY = enum.auto()
    BUSY = enum.auto()
    DEGRADED = enum.auto()
    FAILED = enum.auto()
    STOPPED = enum.auto()


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    """Static descriptive information about a provider.

    All fields are immutable; providers should expose this as read‑only
    data. ``metadata`` can hold arbitrary extra information.
    """

    id: str
    name: str
    version: str
    description: str
    author: str
    state: ProviderState
    capabilities: Mapping[str, Any]
    metadata: Mapping[str, Any]
