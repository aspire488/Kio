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

    PROVIDER_TIMEOUT_S = 5.0  # per-provider attempt cap (was 8s — reduced to bound cascade)
    TOTAL_CHAIN_TIMEOUT_S = 10.0  # total chain budget (was 20s — bounded to prevent 30s+ cascades)
    HARD_MAX_TOKENS = 4096

    _DETERMINISTIC_FALLBACK = (
        "KIO is currently unable to connect to any language model provider. "
        "Please try again later or check your API configurations."
    )

    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}
        self._registry = ProviderFailoverRegistry()
        # Transient-failure retry: a momentary storm of rate limits (429),
        # quota spikes and 5xx across the whole chain (live conversation bug:
        # "I'm not sure how to handle that." after 28s of 429/quota/truncation
        # failures) usually clears within seconds. One bounded chain retry
        # after a short backoff recovers the turn instead of degrading to a
        # canned reply. Never retries when any failure was PERMANENT (auth /
        # 4xx) — those never recover. Cooldown-aware: providers the first
        # pass put into COOLDOWN are skipped by get_chain() on the retry.

    # Bounded transient-failure retry budget (see generate() below).
    _TRANSIENT_RETRY_SLEEP_S = 0.5  # was 1.0
    _TRANSIENT_RETRY_MAX_S = 4.0  # was 12.0 — don't waste chain budget on recovery wait

    async def _chain_with_recovery_wait(self, deadline: float) -> list:
        """Fetch the try-able chain; if empty, wait (bounded) for the soonest
        cooldown expiry and re-fetch once. A rate-limit burst clears in
        seconds — this turns "instant fail for 5 minutes" into "wait a moment,
        then answer" (live bug: "say that again" x3 after a 429 burst).
        """
        chain_now = self._registry.get_chain()
        if chain_now:
            return chain_now
        soonest = self._registry.seconds_until_soonest_recovery()
        if soonest is None:
            return []
        # Cap recovery wait to 2s (was 12s) — don't burn chain budget waiting
        wait = min(soonest, 2.0, self._TRANSIENT_RETRY_MAX_S, max(deadline - time.monotonic(), 0.0))
        if wait > 0.5:
            logger.info(
                "Gateway: chain empty — waiting %.1fs for provider recovery", wait,
            )
            await asyncio.sleep(wait)
        return self._registry.get_chain()

    def register_provider(self, provider: LLMProvider, priority: int = 99) -> None:
        name = provider.provider_name
        self._providers[name] = provider
        self._registry.register(name, priority)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        safe_max_tokens = min(request.max_tokens, self.HARD_MAX_TOKENS)
        provider_timeout = min(request.timeout_s, self.PROVIDER_TIMEOUT_S)
        # FAST/BALANCED/DEEP: short follow-up uses 6s, normal 10s (was 20s), deterministic bypasses altogether
        task = getattr(request, 'task', '') or ''
        _fast = task in ('conversation', 'greeting', 'social') or getattr(request, 'max_tokens', 4096) <= 256
        total_deadline = time.monotonic() + (6.0 if _fast else self.TOTAL_CHAIN_TIMEOUT_S)

        chain = self._registry.get_chain()
        if not chain:
            # All providers in COOLDOWN/DEAD. A rate-limit burst (429 across
            # several providers at once) usually clears within seconds; failing
            # instantly here makes EVERY subsequent message fail for the whole
            # cooldown window (live bug: "say that again" x3 after a 429 burst
            # — the user's messages were fine, the chain was cooling down).
            # Wait for the soonest cooldown expiry, bounded, then re-check.
            chain = await self._chain_with_recovery_wait(total_deadline)
        if not chain:
            logger.warning("Gateway: no providers available in chain")
            self._registry.add_diagnostic(DIAG_CHAIN_EXHAUSTED, "chain", "no providers in chain")
            return self._deterministic_fallback("PROVIDER_CHAIN_EXHAUSTED")

        # Task-tier preference: if the caller requested a specific provider and it is
        # registered & try-able, try it first, then fall through to the priority chain.
        preferred = getattr(request, "preferred_provider", "") or ""
        if preferred and preferred in chain:
            chain = [preferred] + [p for p in chain if p != preferred]
            logger.debug(f"Gateway: task-tier preferred provider '{preferred}' moved to front")

        # One attempt per provider per pass; a bounded second pass is allowed
        # ONLY when every failure was transient (rate limit / quota / 5xx /
        # timeout / truncated / empty) — those clear in seconds. A single
        # permanent failure (auth/4xx) cancels the retry: it never recovers.
        def _is_transient_error(error_code: str) -> bool:
            up = (error_code or "").upper()
            if "429" in up or "RATE_LIMITED" in up or "QUOTA" in up:
                return True
            if "TIMEOUT" in up or "UNREACHABLE" in up or "UNAVAILABLE" in up:
                return True
            if "SERVER_ERROR" in up or "TRUNCATED" in up or "EMPTY" in up:
                return True
            return False

        async def _run_pass(deadline: float, retry_sleep: float = 0.0) -> Optional[LLMResponse]:
            nonlocal_chain = await self._chain_with_recovery_wait(deadline)
            if not nonlocal_chain:
                return None
            if retry_sleep:
                await asyncio.sleep(retry_sleep)
            if preferred and preferred in nonlocal_chain:
                nonlocal_chain = [preferred] + [p for p in nonlocal_chain if p != preferred]
            transient_failures: list[str] = []
            for provider_name in nonlocal_chain:
                if time.monotonic() >= deadline:
                    break
                provider = self._providers.get(provider_name)
                if not provider:
                    continue
                remaining = deadline - time.monotonic()
                effective_timeout = max(min(provider_timeout, remaining), 2.0)
                try:
                    start_time = time.monotonic()
                    response = await asyncio.wait_for(provider.generate(request), timeout=effective_timeout)
                    latency = (time.monotonic() - start_time) * 1000
                    if not response.success:
                        err = response.error_code or "PROVIDER_FAILED"
                        logger.warning(f"Gateway: '{provider_name}' failed: {err} ({latency:.0f}ms)")
                        self._registry.record_failure(provider_name, err)
                        transient_failures.append(err)
                        continue
                    validation_status, validation_error = self._validate_response(response)
                    if validation_status != LLMStatus.SUCCESS:
                        err = validation_error or "VALIDATION_FAILED"
                        logger.warning(f"Gateway: '{provider_name}' validation rejected: {err} ({latency:.0f}ms)")
                        self._registry.record_failure(provider_name, err)
                        transient_failures.append(err)
                        continue
                    self._registry.record_success(provider_name)
                    logger.debug(f"Gateway: success via '{provider_name}' ({latency:.0f}ms)")
                    return response
                except asyncio.TimeoutError:
                    logger.warning(f"Gateway: '{provider_name}' timeout")
                    self._registry.record_failure(provider_name, "TIMEOUT")
                    transient_failures.append("TIMEOUT")
                except Exception as e:
                    logger.warning(f"Gateway: '{provider_name}' error: {type(e).__name__}")
                    self._registry.record_failure(provider_name, f"EXCEPTION: {type(e).__name__}")
                    transient_failures.append("EXCEPTION")
            return None if not transient_failures else transient_failures  # type: ignore[return-value]

        first = await _run_pass(total_deadline)
        if isinstance(first, LLMResponse):
            return first

        # First pass exhausted. Retry once if every recorded failure was
        # transient and enough deadline remains for a meaningful second pass.
        errs = first or []
        remaining_budget = total_deadline - time.monotonic()
        if (
            errs
            and remaining_budget > 2.0  # at least 2s for a quick recovery retry
            and all(_is_transient_error(e) for e in errs)
        ):
            logger.info(
                "Gateway: all %d failures transient — retrying chain once after %.1fs",
                len(errs), self._TRANSIENT_RETRY_SLEEP_S,
            )
            second = await _run_pass(total_deadline, retry_sleep=self._TRANSIENT_RETRY_SLEEP_S)
            if isinstance(second, LLMResponse):
                return second

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
