from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Mapping, Any, Optional


class ProviderStatus(enum.Enum):
    """Result status of a provider action."""

    SUCCESS = enum.auto()
    FAILED = enum.auto()
    PARTIAL = enum.auto()
    CANCELLED = enum.auto()
    TIMEOUT = enum.auto()


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """Encapsulates the outcome of a provider execution.

    ``metadata`` may contain additional implementation‑specific details.
    """

    status: ProviderStatus
    provider: str  # Identifier of the provider that produced this result
    action: str  # Name of the action invoked
    data: Any  # Payload returned by the provider (if any)
    duration_ms: int
    error: Optional[Exception]
    metadata: Mapping[str, Any]
