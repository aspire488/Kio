import asyncio
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus
from mini_kio.llm.provider_base import LLMProvider


class MockLLMProvider(LLMProvider):
    """
    Deterministic mock provider for Gate 3A validation.
    No network access.
    """

    def __init__(self, mode: str = "success"):
        self.mode = mode
        self._generate_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self._generate_count += 1
        
        if self.mode == "timeout_storm":
            # Always timeout
            await asyncio.sleep(2.0)
            return LLMResponse(False, LLMStatus.TIMEOUT, "", provider=self.provider_name)

        if self.mode == "malformed_json":
            return LLMResponse(True, LLMStatus.SUCCESS, '{"intent_type": "executable", "action": "open"', provider=self.provider_name)

        if self.mode == "partial_response":
            return LLMResponse(True, LLMStatus.SUCCESS, "I am sorry, I cannot com...", provider=self.provider_name)

        if self.mode == "transient_failure":
            # Fail every other request
            if self._generate_count % 2 == 1:
                raise Exception("Transient network error")
            return self._success_response(request)

        if self.mode == "unavailable":
            return LLMResponse(False, LLMStatus.ERROR, "", error_code="SERVICE_UNAVAILABLE", provider=self.provider_name)

        if self.mode == "timeout":
            await asyncio.sleep(request.timeout_s + 1)
            return LLMResponse(False, LLMStatus.TIMEOUT, "", provider=self.provider_name)

        if self.mode == "fail":
            raise Exception("Simulated provider failure")

        if self.mode == "non_retryable":
            return LLMResponse(
                False, LLMStatus.ERROR, "",
                error_code="GEMINI_QUOTA_EXCEEDED", provider=self.provider_name
            )

        if self.mode == "invalid_key":
            return LLMResponse(
                False, LLMStatus.ERROR, "",
                error_code="INVALID_API_KEY", provider=self.provider_name
            )

        if self.mode == "empty":
            return LLMResponse(True, LLMStatus.SUCCESS, "", provider=self.provider_name)

        if self.mode == "malformed":
            return LLMResponse(True, LLMStatus.MALFORMED, "{}", provider=self.provider_name)

        # Default success mode
        return self._success_response(request)

    def _success_response(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            success=True,
            status=LLMStatus.SUCCESS,
            content=f"Mock response for: {request.prompt[:20]}...",
            latency_ms=10.0,
            token_usage={"total_tokens": 15},
            provider=self.provider_name
        )

    async def health_check(self) -> bool:
        return True
