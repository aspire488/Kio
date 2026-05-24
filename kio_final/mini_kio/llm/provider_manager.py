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

    def register_provider(self, name: str):
        if name not in self._metrics:
            self._metrics[name] = ProviderMetrics()
            self._providers.append(name)

    def select_provider(self, requested: Optional[str] = None) -> Optional[str]:
        """Selects a healthy provider, favoring the requested one if healthy."""
        current_time = time.time()
        
        # 1. Try requested provider
        if requested and self._is_healthy(requested, current_time):
            return requested

        # 2. Try default (first) or others
        for name in self._providers:
            if self._is_healthy(name, current_time):
                return name
        
        return None

    def record_success(self, name: str):
        if name not in self._metrics: return
        m = self._metrics[name]
        m.total_requests += 1
        m.consecutive_failures = 0
        m.last_success_timestamp = time.time()

    def record_failure(self, name: str, status: LLMStatus):
        if name not in self._metrics: return
        m = self._metrics[name]
        m.total_requests += 1
        m.consecutive_failures += 1
        m.last_failure_timestamp = time.time()

        if status == LLMStatus.TIMEOUT:
            m.timeout_count += 1
        elif status == LLMStatus.MALFORMED:
            m.malformed_count += 1

        # Check circuit breaker
        if (m.consecutive_failures >= self.FAILURE_THRESHOLD or 
            m.timeout_count >= self.TIMEOUT_THRESHOLD or 
            m.malformed_count >= self.MALFORMED_THRESHOLD):
            self._enter_cooldown(name, m)

    def get_health_status(self, name: str) -> ProviderHealthStatus:
        if name not in self._metrics: return ProviderHealthStatus.DOWN
        m = self._metrics[name]
        current_time = time.time()
        
        if m.cooldown_until > current_time:
            return ProviderHealthStatus.COOLDOWN
        if m.consecutive_failures > 0:
            return ProviderHealthStatus.UNSTABLE
        return ProviderHealthStatus.HEALTHY

    def _is_healthy(self, name: str, current_time: float) -> bool:
        if name not in self._metrics: return False
        m = self._metrics[name]
        return m.cooldown_until <= current_time

    def _enter_cooldown(self, name: str, metrics: ProviderMetrics):
        metrics.cooldown_until = time.time() + self.COOLDOWN_DURATION_S
        # We don't reset counters here, allowing the cooldown to expire naturally
        # but we could reset consecutive_failures if we wanted to allow immediate retry after cooldown
        metrics.consecutive_failures = 0 
