"""
llm_gateway.py — Multi-Provider Failover Gateway

Chain-based failover across priority-ordered providers.
One attempt per provider (no per-provider retries).
Total chain timeout prevents hanging.
Chain exhaustion → deterministic degraded response.
"""

import asyncio
import logging
import json
import time
from typing import Dict, Optional
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus
from mini_kio.llm.provider_base import LLMProvider
from mini_kio.llm.provider_registry import (
    ProviderFailoverRegistry, ProviderState,
    DIAG_CHAIN_EXHAUSTED,
)

logger = logging.getLogger(__name__)


class LLMGateway:
    """
    Multi-provider failover gateway with chain-based fallback.

    Rules:
        - Providers tried in priority order (0 = highest)
        - Exactly 1 attempt per provider (no per-provider retries)
        - Skip COOLDOWN and DEAD providers
        - Total chain timeout prevents hanging
        - All providers exhausted → deterministic degraded response
    """

    PROVIDER_TIMEOUT_S = 15.0
    TOTAL_CHAIN_TIMEOUT_S = 45.0
    HARD_MAX_TOKENS = 4096

    _DETERMINISTIC_FALLBACK = (
        "KIO is currently unable to connect to any language model provider. "
        "Please try again later or check your API configurations."
    )

    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}
        self._registry = ProviderFailoverRegistry()

    def register_provider(self, provider: LLMProvider, priority: int = 99) -> None:
        name = provider.provider_name
        self._providers[name] = provider
        self._registry.register(name, priority)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        safe_max_tokens = min(request.max_tokens, self.HARD_MAX_TOKENS)
        provider_timeout = min(request.timeout_s, self.PROVIDER_TIMEOUT_S)
        total_deadline = time.monotonic() + self.TOTAL_CHAIN_TIMEOUT_S

        chain = self._registry.get_chain()
        if not chain:
            logger.warning("Gateway: no providers available in chain")
            self._registry.add_diagnostic(DIAG_CHAIN_EXHAUSTED, "chain", "no providers in chain")
            return self._deterministic_fallback("PROVIDER_CHAIN_EXHAUSTED")

        for provider_name in chain:
            if time.monotonic() >= total_deadline:
                logger.warning(f"Gateway: total chain timeout reached, tried up to '{provider_name}'")
                break

            provider = self._providers.get(provider_name)
            if not provider:
                continue

            remaining = total_deadline - time.monotonic()
            effective_timeout = max(min(provider_timeout, remaining), 2.0)

            try:
                start_time = time.monotonic()
                response = await asyncio.wait_for(
                    provider.generate(request),
                    timeout=effective_timeout,
                )
                latency = (time.monotonic() - start_time) * 1000

                if not response.success:
                    err = response.error_code or "PROVIDER_FAILED"
                    logger.warning(
                        f"Gateway: '{provider_name}' failed: {err} ({latency:.0f}ms)"
                    )
                    self._registry.record_failure(provider_name, err)
                    continue

                validation_status, validation_error = self._validate_response(response)
                if validation_status != LLMStatus.SUCCESS:
                    err = validation_error or "VALIDATION_FAILED"
                    logger.warning(
                        f"Gateway: '{provider_name}' validation rejected: {err} ({latency:.0f}ms)"
                    )
                    self._registry.record_failure(provider_name, err)
                    continue

                self._registry.record_success(provider_name)
                logger.debug(f"Gateway: success via '{provider_name}' ({latency:.0f}ms)")
                return response

            except asyncio.TimeoutError:
                logger.warning(f"Gateway: '{provider_name}' timeout")
                self._registry.record_failure(provider_name, "TIMEOUT")
            except Exception as e:
                logger.warning(f"Gateway: '{provider_name}' error: {type(e).__name__}")
                self._registry.record_failure(provider_name, f"EXCEPTION: {type(e).__name__}")

        logger.warning("Gateway: all providers exhausted")
        self._registry.add_diagnostic(DIAG_CHAIN_EXHAUSTED, "chain", "all providers failed")
        return self._deterministic_fallback("PROVIDER_CHAIN_EXHAUSTED")

    def _validate_response(self, response: LLMResponse) -> tuple[LLMStatus, Optional[str]]:
        if not isinstance(response, LLMResponse):
            return LLMStatus.ERROR, "NOT_LLM_RESPONSE"
        if not response.success:
            return LLMStatus.ERROR, response.error_code or "PROVIDER_FAILED"
        if not response.content or not response.content.strip():
            return LLMStatus.MALFORMED, "EMPTY_RESPONSE"
        if len(response.content) > 100000:
            return LLMStatus.MALFORMED, "RESPONSE_TOO_LARGE"
        is_intent = "intent_type" in response.content
        if is_intent:
            try:
                json_start = response.content.find("{")
                json_end = response.content.rfind("}") + 1
                if json_start == -1 or json_end == 0:
                    return LLMStatus.MALFORMED, "MISSING_JSON_BRACES"
                else:
                    json.loads(response.content[json_start:json_end])
            except json.JSONDecodeError:
                return LLMStatus.MALFORMED, "INVALID_JSON_STRUCTURE"
        return LLMStatus.SUCCESS, None

    def _deterministic_fallback(self, error_code: str) -> LLMResponse:
        return LLMResponse(
            success=False,
            status=LLMStatus.DEGRADED,
            content=self._DETERMINISTIC_FALLBACK,
            error_code=error_code,
            provider="fallback",
        )

    def _degraded_response(self, error_code: str, provider: str, status: LLMStatus = LLMStatus.DEGRADED) -> LLMResponse:
        """Legacy alias kept for backward compatibility with existing tests."""
        return self._deterministic_fallback(error_code)

    def get_registry(self) -> ProviderFailoverRegistry:
        return self._registry

    def get_diagnostics(self) -> list:
        return self._registry.get_diagnostics()
