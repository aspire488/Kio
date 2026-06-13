"""
provider_registry.py — Multi-Provider Failover Chain

Priority-ordered failover chain with health state tracking, cooldown, and diagnostics.
Provider order (lower priority number = higher priority):

    0: Gemini (Google AI direct)
    1: Groq (direct OpenAI-compatible API)
    2: OpenRouter (multi-model gateway)
    3: Together AI
    4: Cerebras

FreeLLM is optional experimental backend (ENABLE_FREELLM=true), not in default chain.

Chain behavior:
    - Try providers in priority order
    - Skip COOLDOWN and DEAD providers
    - One attempt per provider (no per-provider retries)
    - Failed providers: HEALTHY → DEGRADED → COOLDOWN → auto-recover
    - Permanent errors (auth): DEAD (never retry)
    - Chain exhaustion → deterministic offline fallback
"""

import time
import logging
from enum import Enum
from typing import Optional, List, Dict
from dataclasses import dataclass, field
from mini_kio.llm.models import ProviderState

logger = logging.getLogger(__name__)

# ── Diagnostic event codes ──────────────────────────────────────────

DIAG_PROVIDER_SELECTED = "provider_selected"
DIAG_PROVIDER_FAILED = "provider_failed"
DIAG_PROVIDER_SKIPPED = "provider_skipped_cooldown"
DIAG_COOLDOWN_STARTED = "provider_cooldown_started"
DIAG_CHAIN_EXHAUSTED = "provider_chain_exhausted"
DIAG_PROVIDER_RECOVERED = "provider_recovered"
DIAG_PROVIDER_DEAD = "provider_dead"
DIAG_PROVIDER_CHAIN_EMPTY = "provider_chain_empty"
DIAG_PROVIDER_RECOVERY_ATTEMPTED = "provider_recovery_attempted"
DIAG_PROVIDER_HEALTH_TRANSITION = "provider_health_transition"


@dataclass
class DiagnosticRecord:
    event: str
    provider: str
    detail: str = ""
    timestamp: float = 0.0


class ProviderPriority(int, Enum):
    GEMINI = 0
    GROQ = 1
    CEREBRAS = 2
    SAMBANOVA = 3
    FIREWORKS = 4
    HUGGINGFACE = 5
    OPENROUTER = 6
    TOGETHER_AI = 7


_PERMANENT_ERROR_PATTERNS = (
    "INVALID_API_KEY", "AUTH_FAILED", "PERMISSION_DENIED",
    "GEMINI_AUTH_ERROR", "GEMINI_NOT_CONFIGURED", "GEMINI_MODEL_NOT_FOUND",
    "HUGGINGFACE_AUTH_ERROR", "HUGGINGFACE_MODEL_NOT_FOUND", "HUGGINGFACE_NOT_CONFIGURED",
    "API_KEY_INVALID", "UNAUTHORIZED", "FORBIDDEN",
    "404", "NOT_FOUND", "INVALID_MODEL",
)


def _is_permanent_error(error_code: str) -> bool:
    upper = error_code.upper()
    for pat in _PERMANENT_ERROR_PATTERNS:
        if pat in upper:
            return True
    return False


class ProviderFailoverRegistry:
    """
    Priority-ordered failover chain with health tracking and diagnostics.

    Rules:
        - register(name, priority) adds a provider
        - get_chain() returns try-able providers in priority order
        - record_success() resets failure count
        - record_failure() transitions state based on error type
        - Cooldown: 60s after COOLDOWN_THRESHOLD failures
        - Auto-recover: cooldown expiry → HEALTHY
    """

    COOLDOWN_DURATION_S = 60
    DEGRADE_THRESHOLD = 1
    COOLDOWN_THRESHOLD = 3

    COOLDOWN_RATE_LIMIT_S = 300
    COOLDOWN_QUOTA_S = 1800
    COOLDOWN_TIMEOUT_S = 120

    def __init__(self):
        self._providers: List[str] = []
        self._priority_map: Dict[str, int] = {}
        self._states: Dict[str, ProviderState] = {}
        self._failures: Dict[str, int] = {}
        self._last_error: Dict[str, str] = {}
        self._last_error_time: Dict[str, float] = {}
        self._cooldown_until: Dict[str, float] = {}
        self._diagnostics: List[DiagnosticRecord] = []

    def register(self, name: str, priority: int) -> None:
        if name in self._states:
            logger.warning(f"ProviderRegistry: '{name}' already registered, skipping")
            return
        self._providers.append(name)
        self._priority_map[name] = priority
        self._providers.sort(key=lambda n: self._priority_map.get(n, 99))
        self._states[name] = ProviderState.HEALTHY
        self._failures[name] = 0
        self._last_error[name] = ""
        self._last_error_time[name] = 0.0
        self._cooldown_until[name] = 0.0
        logger.info(f"ProviderRegistry: registered '{name}' at priority {priority}")

    def add_diagnostic(self, event: str, provider: str, detail: str = "") -> None:
        self._diagnostics.append(DiagnosticRecord(
            event=event, provider=provider,
            detail=detail, timestamp=time.time(),
        ))

    def get_chain(self) -> List[str]:
        now = time.time()
        chain: List[str] = []
        for name in list(self._providers):
            state = self._states.get(name, ProviderState.DEAD)
            if state == ProviderState.COOLDOWN:
                if self._cooldown_until.get(name, 0) <= now:
                    self._states[name] = ProviderState.HEALTHY
                    self._failures[name] = 0
                    self._last_error[name] = ""
                    self._last_error_time[name] = 0.0
                    logger.info(f"Provider cooldown expired: {name} recovered to HEALTHY")
                    self._diagnostics.append(DiagnosticRecord(
                        event=DIAG_PROVIDER_RECOVERY_ATTEMPTED, provider=name,
                        detail="cooldown expired — attempting recovery", timestamp=now,
                    ))
                    self._diagnostics.append(DiagnosticRecord(
                        event=DIAG_PROVIDER_RECOVERED, provider=name,
                        detail="cooldown expired, recovered", timestamp=now,
                    ))
                    chain.append(name)
                else:
                    remaining = self._cooldown_until.get(name, 0) - now
                    logger.info(f"Provider cooldown active: {name} skipped ({remaining:.0f}s remaining)")
                    self._diagnostics.append(DiagnosticRecord(
                        event=DIAG_PROVIDER_SKIPPED, provider=name,
                        detail=f"cooldown {remaining:.0f}s remaining", timestamp=now,
                    ))
            elif state == ProviderState.DEAD:
                self._diagnostics.append(DiagnosticRecord(
                    event=DIAG_PROVIDER_SKIPPED, provider=name,
                    detail="DEAD — permanent error", timestamp=now,
                ))
            else:
                chain.append(name)
        if not chain:
            self._diagnostics.append(DiagnosticRecord(
                event=DIAG_PROVIDER_CHAIN_EMPTY, provider="system",
                detail="no try-able providers in chain", timestamp=now,
            ))
        return chain

    def record_success(self, name: str) -> None:
        if name not in self._states:
            return
        self._failures[name] = 0
        self._last_error[name] = ""
        self._last_error_time[name] = 0.0
        self._states[name] = ProviderState.HEALTHY
        self._diagnostics.append(DiagnosticRecord(
            event=DIAG_PROVIDER_SELECTED, provider=name,
            detail="success", timestamp=time.time(),
        ))

    def record_failure(self, name: str, error_code: str) -> ProviderState:
        if name not in self._states:
            return ProviderState.DEAD
        now = time.time()
        self._failures[name] = self._failures.get(name, 0) + 1
        self._last_error[name] = error_code
        self._last_error_time[name] = now
        fail_count = self._failures[name]

        if _is_permanent_error(error_code):
            self._states[name] = ProviderState.DEAD
            self._diagnostics.append(DiagnosticRecord(
                event=DIAG_PROVIDER_DEAD, provider=name,
                detail=f"permanent: {error_code}", timestamp=now,
            ))
            return ProviderState.DEAD

        self._diagnostics.append(DiagnosticRecord(
            event=DIAG_PROVIDER_FAILED, provider=name,
            detail=f"{error_code} (failure #{fail_count})", timestamp=now,
        ))

        if fail_count >= self.COOLDOWN_THRESHOLD:
            cooldown = self._get_cooldown_duration(error_code)
            self._states[name] = ProviderState.COOLDOWN
            self._cooldown_until[name] = now + cooldown
            self._diagnostics.append(DiagnosticRecord(
                event=DIAG_COOLDOWN_STARTED, provider=name,
                detail=f"failures={fail_count}, error={error_code}, cooldown={cooldown}s",
                timestamp=now,
            ))
            return ProviderState.COOLDOWN

        if fail_count >= self.DEGRADE_THRESHOLD:
            self._states[name] = ProviderState.DEGRADED
            self._diagnostics.append(DiagnosticRecord(
                event=DIAG_PROVIDER_HEALTH_TRANSITION, provider=name,
                detail=f"health degraded: {error_code} (failure #{fail_count})", timestamp=now,
            ))

        return self._states[name]

    def _get_cooldown_duration(self, error_code: str) -> int:
        upper = error_code.upper()
        if "RATE_LIMITED" in upper or "429" in upper:
            return self.COOLDOWN_RATE_LIMIT_S
        if "QUOTA" in upper:
            return self.COOLDOWN_QUOTA_S
        if "TIMEOUT" in upper:
            return self.COOLDOWN_TIMEOUT_S
        return self.COOLDOWN_DURATION_S

    def get_state(self, name: str) -> ProviderState:
        return self._states.get(name, ProviderState.DEAD)

    def get_diagnostics(self) -> List[DiagnosticRecord]:
        return list(self._diagnostics)

    def clear_diagnostics(self) -> None:
        self._diagnostics.clear()

    def get_providers(self) -> List[str]:
        return list(self._providers)

    def get_failure_count(self, name: str) -> int:
        return self._failures.get(name, 0)

    def get_last_error(self, name: str) -> str:
        return self._last_error.get(name, "")

    def get_last_error_time(self, name: str) -> float:
        return self._last_error_time.get(name, 0.0)

    def snapshot(self) -> dict:
        """Immutable registry snapshot for chain integrity validation."""
        return {
            "providers": list(self._providers),
            "states": dict(self._states),
            "failures": dict(self._failures),
            "last_error": dict(self._last_error),
            "last_error_time": dict(self._last_error_time),
            "priorities": dict(self._priority_map),
        }

    def reset(self) -> None:
        self._providers.clear()
        self._states.clear()
        self._failures.clear()
        self._last_error.clear()
        self._last_error_time.clear()
        self._cooldown_until.clear()
        self._diagnostics.clear()
