"""ExecutionProvider contract — every capability exposes through this interface."""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class ProviderHealth(enum.Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class ExecutionStatus(enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ProviderCapability:
    name: str
    category: str = "unknown"
    timeout_s: float = 10.0
    ram_budget_mb: int = 10


class ExecutionProvider(ABC):
    """Contract that every execution provider must implement."""

    @abstractmethod
    def id(self) -> str: ...

    @abstractmethod
    def capabilities(self) -> list[ProviderCapability]: ...

    @abstractmethod
    def health(self) -> ProviderHealth: ...

    def permissions(self) -> dict[str, Any]:
        return {}

    def estimate(self, action: str, target: str) -> dict[str, Any]:
        return {"estimated_ms": 1000, "action": action, "target": target}

    @abstractmethod
    def execute(self, action: str, target: str, **kwargs: Any) -> dict[str, Any]: ...

    def verify(self, action: str, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("verification_status", "passed" if result.get("success") else "failed")
        result.setdefault("probe_used", "default")
        return result

    def cancel(self, execution_id: str) -> dict[str, Any]:
        return {"success": False, "message": f"Cancel not supported by {self.id()}"}

    def pause(self, execution_id: str) -> dict[str, Any]:
        return {"success": False, "message": f"Pause not supported by {self.id()}"}

    def resume(self, execution_id: str) -> dict[str, Any]:
        return {"success": False, "message": f"Resume not supported by {self.id()}"}

    def status(self, execution_id: str) -> dict[str, Any]:
        return {"status": "unknown", "provider": self.id()}
