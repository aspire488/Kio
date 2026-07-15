"""Health reporting interfaces.

Defines a simple structure for runtime health checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Any

class HealthStatus(Enum):
    """Overall health status indicators."""
    UNKNOWN = auto()
    HEALTHY = auto()
    UNHEALTHY = auto()
    DEGRADED = auto()

@dataclass(frozen=True)
class HealthReport:
    """Container for health check results.

    Attributes:
        status: Overall :class:`HealthStatus`.
        details: Optional free‑form details about the health check.
        components: Optional per‑component health information.
    """

    status: HealthStatus
    details: str | None = None
    components: List[Any] | None = None

# ponytail: Components field loosely typed; concrete implementations can refine the type.
