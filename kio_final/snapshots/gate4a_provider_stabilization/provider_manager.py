import time
from typing import Dict, List, Optional
from .models import ProviderHealthStatus, ProviderMetrics, LLMStatus, LLMResponse


class ProviderManager:
    """
    Manages provider lifecycle, health tracking, and circuit breaking.
    Deterministic behavior only.
    """

    FAILURE_THRESHOLD = 3
    COOLDOWN_DURATION_S = 60
    TIMEOUT_THRESHOLD = 5
    MALFORMED_THRESHOLD = 3

    def __init__(self):
        self._metrics: Dict[str, ProviderMetrics] = {}
        self._providers: List[str] = []

    def register_provider(self, name: str, replace: bool = False):
        """
        Register a provider with validated name.
        Default (replace=False): raises ValueError on duplicate.
        replace=True: silently replaces and resets metrics to clean state.
        """
        if not name or not name.strip():
            raise ValueError(f"Invalid provider name: '{name}'")
        name = name.strip()
        if name in self._metrics:
            if not replace:
                raise ValueError(f"Provider '{name}' already registered")
            self._metrics[name] = ProviderMetrics()
            return
        self._metrics[name] = ProviderMetrics()
        self._providers.append(name)

    def select_provider(self, requested: Optional[str] = None) -> Optional[str]:
        """
        Selects a healthy provider.
        Ordering: requested (if healthy) -> registration order.
        Stable across calls — determined solely by registration order.
        """
        current_time = time.time()

        if requested and self._is_healthy(requested, current_time):
            return requested

        for name in self._providers:
            if self._is_healthy(name, current_time):
                return name

        return None

    def record_success(self, name: str):
        """Record a successful provider call. Silent no-op on missing provider."""
        if not name or not name.strip():
            raise ValueError(f"Invalid provider name: '{name}'")
        if name not in self._metrics:
            return
        m = self._metrics[name]
        m.total_requests += 1
        m.consecutive_failures = 0
        m.last_success_timestamp = time.time()

    def record_failure(self, name: str, status: LLMStatus):
        """Record a failed provider call. Silent no-op on missing provider."""
        if not name or not name.strip():
            raise ValueError(f"Invalid provider name: '{name}'")
        if name not in self._metrics:
            return
        m = self._metrics[name]
        m.total_requests += 1
        m.consecutive_failures += 1
        m.last_failure_timestamp = time.time()

        if status == LLMStatus.TIMEOUT:
            m.timeout_count += 1
        elif status == LLMStatus.MALFORMED:
            m.malformed_count += 1

        if (m.consecutive_failures >= self.FAILURE_THRESHOLD or
            m.timeout_count >= self.TIMEOUT_THRESHOLD or
            m.malformed_count >= self.MALFORMED_THRESHOLD):
            self._enter_cooldown(name, m)

    def get_health_status(self, name: str) -> ProviderHealthStatus:
        """Determine health status for a provider. Unregistered returns DOWN."""
        if not name or not name.strip():
            raise ValueError(f"Invalid provider name: '{name}'")
        if name not in self._metrics:
            return ProviderHealthStatus.DOWN
        m = self._metrics[name]
        current_time = time.time()

        if m.cooldown_until > current_time:
            return ProviderHealthStatus.COOLDOWN
        if m.consecutive_failures > 0:
            return ProviderHealthStatus.UNSTABLE
        return ProviderHealthStatus.HEALTHY

    def expire_cooldown(self, name: str):
        """
        Explicitly expire cooldown for deterministic test transitions.
        After expiry, provider returns to UNSTABLE (if failures) or HEALTHY.
        Raises ValueError if provider not registered.
        """
        if not name or not name.strip():
            raise ValueError(f"Invalid provider name: '{name}'")
        if name not in self._metrics:
            raise ValueError(f"Provider '{name}' not registered")
        m = self._metrics[name]
        if m.cooldown_until <= time.time():
            return
        m.cooldown_until = time.time()

    def _is_healthy(self, name: str, current_time: float) -> bool:
        if name not in self._metrics:
            return False
        m = self._metrics[name]
        return m.cooldown_until <= current_time

    def _enter_cooldown(self, name: str, metrics: ProviderMetrics):
        metrics.cooldown_until = time.time() + self.COOLDOWN_DURATION_S
        metrics.consecutive_failures = 0
