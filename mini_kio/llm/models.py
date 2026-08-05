from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any


class LLMStatus(Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    DEGRADED = "degraded"
    MALFORMED = "malformed"
    COOLDOWN = "cooldown"


class ProviderHealthStatus(Enum):
    HEALTHY = "healthy"
    UNSTABLE = "unstable"
    DOWN = "down"
    COOLDOWN = "cooldown"


class ProviderState(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    COOLDOWN = "cooldown"
    DEAD = "dead"


@dataclass
class DiagnosticEvent:
    event: str
    provider: str
    detail: str = ""
    timestamp: float = 0.0


@dataclass
class ProviderMetrics:
    total_requests: int = 0
    consecutive_failures: int = 0
    timeout_count: int = 0
    malformed_count: int = 0
    last_success_timestamp: float = 0.0
    last_failure_timestamp: float = 0.0
    cooldown_until: float = 0.0
    failure_rate: float = 0.0


@dataclass(frozen=True)
class LLMRequest:
    prompt: str
    max_tokens: int = 4096
    timeout_s: float = 30.0
    provider: str = "mock"
    metadata: Dict[str, Any] = field(default_factory=dict)
    preferred_provider: str = ""


@dataclass(frozen=True)
class LLMResponse:
    success: bool
    status: LLMStatus
    content: str
    error_code: Optional[str] = None
    latency_ms: float = 0.0
    token_usage: Dict[str, int] = field(default_factory=dict)
    provider: str = "unknown"


@dataclass(frozen=True)
class LLMError:
    code: str
    message: str
    retryable: bool = False
