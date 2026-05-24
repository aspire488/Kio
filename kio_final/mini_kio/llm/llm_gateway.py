import asyncio
import time
import json
from typing import Dict, Optional, Type
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus
from mini_kio.llm.provider_base import LLMProvider
from mini_kio.llm.provider_manager import ProviderManager


class LLMGateway:
    """
    Harden LLM Gateway for Gate 3C.
    Acts as a strict containment layer with circuit breaking and reliability.
    """

    MAX_RETRIES = 3
    HARD_TIMEOUT_S = 30.0
    HARD_MAX_TOKENS = 4096
    INITIAL_BACKOFF_S = 0.5
    MAX_BACKOFF_S = 5.0

    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}
        self._manager = ProviderManager()

    def register_provider(self, provider: LLMProvider, is_default: bool = False):
        """Register a bounded provider."""
        name = provider.provider_name
        self._providers[name] = provider
        self._manager.register_provider(name)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Bounded generation with circuit breaking and exponential backoff.
        """
        safe_max_tokens = min(request.max_tokens, self.HARD_MAX_TOKENS)
        safe_timeout = min(request.timeout_s, self.HARD_TIMEOUT_S)

        # Provider selection via manager
        provider_name = self._manager.select_provider(request.provider)
        if not provider_name:
            return self._degraded_response("NO_PROVIDER_AVAILABLE", "gateway")

        provider = self._providers[provider_name]
        last_status = LLMStatus.ERROR
        last_error = "UNKNOWN"

        for attempt in range(self.MAX_RETRIES):
            try:
                start_time = time.monotonic()
                response = await asyncio.wait_for(
                    provider.generate(request),
                    timeout=safe_timeout
                )
                latency = (time.monotonic() - start_time) * 1000

                # Strict Parsing & Validation
                validation_status, validation_error = self._validate_response(response)
                if validation_status != LLMStatus.SUCCESS:
                    self._manager.record_failure(provider_name, validation_status)
                    last_status = validation_status
                    last_error = validation_error
                    if attempt < self.MAX_RETRIES - 1:
                        await self._backoff(attempt)
                        continue
                    return self._degraded_response(validation_error, provider_name)

                # Success Path
                self._manager.record_success(provider_name)
                return response

            except asyncio.TimeoutError:
                self._manager.record_failure(provider_name, LLMStatus.TIMEOUT)
                last_status = LLMStatus.TIMEOUT
                last_error = "TIMEOUT"
            except Exception as e:
                self._manager.record_failure(provider_name, LLMStatus.ERROR)
                last_status = LLMStatus.ERROR
                last_error = f"PROVIDER_ERROR: {str(e)[:50]}"

            if attempt < self.MAX_RETRIES - 1:
                await self._backoff(attempt)

        return self._degraded_response(last_error, provider_name)

    def _validate_response(self, response: LLMResponse) -> tuple[LLMStatus, Optional[str]]:
        """Hardened validation of provider output."""
        if not response.success:
            return LLMStatus.ERROR, response.error_code
        
        if not response.content or not response.content.strip():
            return LLMStatus.MALFORMED, "EMPTY_RESPONSE"
        
        if len(response.content) > 100000: # Arbitrary hard limit
            return LLMStatus.MALFORMED, "RESPONSE_TOO_LARGE"

        # If it claims to be JSON, try to parse it
        has_braces = "{" in response.content and "}" in response.content
        is_intent = "intent_type" in response.content

        if is_intent or has_braces:
            try:
                json_start = response.content.find("{")
                json_end = response.content.rfind("}") + 1
                if json_start == -1 or json_end == 0:
                    if is_intent: return LLMStatus.MALFORMED, "MISSING_JSON_BRACES"
                else:
                    json.loads(response.content[json_start:json_end])
            except json.JSONDecodeError:
                return LLMStatus.MALFORMED, "INVALID_JSON_STRUCTURE"

        return LLMStatus.SUCCESS, None

    async def _backoff(self, attempt: int):
        """Exponential backoff logic."""
        delay = min(self.INITIAL_BACKOFF_S * (2 ** attempt), self.MAX_BACKOFF_S)
        await asyncio.sleep(delay)

    def _degraded_response(self, error_code: str, provider: str, status: LLMStatus = LLMStatus.DEGRADED) -> LLMResponse:
        """Return a safe, bounded degraded response."""
        return LLMResponse(
            success=False,
            status=status,
            content="[DEGRADED MODE] LLM unavailable or malformed response.",
            error_code=error_code,
            provider=provider
        )
