import logging
import asyncio
import os
from typing import Optional
from mini_kio.llm.provider_base import LLMProvider
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class HuggingFaceProvider(LLMProvider):
    """
    Bounded Hugging Face conversational provider via OpenAI-compatible endpoint.
    Text-in / text-out only. No tools, no streaming, no autonomous behavior.
    Uses Hugging Face Router for OpenAI-compatible inference.
    """

    def __init__(self, api_key: str, timeout_s: float = 15.0, max_tokens: int = 200, model_name: str = "Qwen/Qwen3-32B"):
        self._api_key = api_key
        self._default_timeout_s = timeout_s
        self._default_max_tokens = max_tokens
        self._model_name = model_name
        self._client = None
        if OpenAI and api_key:
            try:
                self._client = OpenAI(
                    base_url="https://router.huggingface.co/v1",
                    api_key=api_key,
                    timeout=timeout_s,
                )
                logger.info("HuggingFace provider: client initialized successfully.")
            except Exception as e:
                logger.error(f"HuggingFace provider: Failed to initialize OpenAI client: {e}")
                self._client = None

    @property
    def provider_name(self) -> str:
        return "huggingface"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if self._client is None:
            logger.warning("HuggingFace provider generate: client is None (not configured)")
            return LLMResponse(
                success=False,
                status=LLMStatus.ERROR,
                content="",
                error_code="HUGGINGFACE_NOT_CONFIGURED",
                provider=self.provider_name,
            )

        safe_timeout = min(request.timeout_s, self._default_timeout_s)
        safe_max_tokens = min(request.max_tokens, self._default_max_tokens)

        try:
            chat_completion = await asyncio.wait_for(
                self._call_huggingface(request.prompt, safe_max_tokens),
                timeout=safe_timeout,
            )
            
            if chat_completion and chat_completion.choices and chat_completion.choices[0].message.content:
                content = chat_completion.choices[0].message.content
                # A stream cut by max_tokens must NOT be returned as success:
                # the provider would silently surface a half-sentence
                # ("I'd highlight its engineering rigor, particularly") as a
                # complete reply. finish_reason='length' means truncated —
                # reject it so the gateway chain falls through to the next
                # provider instead of serving a broken answer.
                try:
                    _finish = getattr(chat_completion.choices[0], "finish_reason", None)
                except Exception:
                    _finish = None
                if _finish == "length":
                    logger.warning("HuggingFace provider generate: truncated by max_tokens (finish_reason=length)")
                    return LLMResponse(
                        success=False,
                        status=LLMStatus.MALFORMED,
                        content="",
                        error_code="HUGGINGFACE_TRUNCATED",
                        provider=self.provider_name,
                    )
                logger.debug(f"HuggingFace provider generate: success, content_len={len(content)}")
                return LLMResponse(
                    success=True,
                    status=LLMStatus.SUCCESS,
                    content=content,
                    provider=self.provider_name,
                )
            else:
                logger.warning("HuggingFace provider generate: empty or malformed response")
                return LLMResponse(
                    success=False,
                    status=LLMStatus.MALFORMED,
                    content="",
                    error_code="HUGGINGFACE_EMPTY_RESPONSE",
                    provider=self.provider_name,
                )

        except asyncio.TimeoutError:
            logger.warning("HuggingFace provider generate: timeout")
            return LLMResponse(
                success=False,
                status=LLMStatus.TIMEOUT,
                content="",
                error_code="HUGGINGFACE_TIMEOUT",
                provider=self.provider_name,
            )
        except Exception as e:
            error_str = str(e)[:120]
            error_type = type(e).__name__
            logger.warning(f"HuggingFace provider generate: exception: {error_type} - {error_str[:60]}")

            if "401" in error_str or "unauthorized" in error_str.lower():
                 return LLMResponse(
                    success=False,
                    status=LLMStatus.ERROR,
                    content="",
                    error_code="HUGGINGFACE_AUTH_ERROR",
                    provider=self.provider_name,
                )
            elif "404" in error_str or "model" in error_str.lower() and ("not found" in error_str.lower() or "unavailable" in error_str.lower()):
                 return LLMResponse(
                    success=False,
                    status=LLMStatus.ERROR,
                    content="",
                    error_code="HUGGINGFACE_MODEL_NOT_FOUND",
                    provider=self.provider_name,
                )
            elif "rate limit" in error_str.lower() or "quota" in error_str.lower() or "429" in error_str:
                 return LLMResponse(
                    success=False,
                    status=LLMStatus.DEGRADED,
                    content="",
                    error_code="HUGGINGFACE_QUOTA_EXCEEDED",
                    provider=self.provider_name,
                )
            
            return LLMResponse(
                success=False,
                status=LLMStatus.ERROR,
                content="",
                error_code=f"HUGGINGFACE_ERROR: {error_str[:60]}",
                provider=self.provider_name,
            )

    async def health_check(self) -> bool:
        # A simple health check could be to try to list models if the API supports it,
        # or just check if the client was initialized successfully.
        return self._client is not None

    async def _call_huggingface(self, prompt: str, max_tokens: int):
        # The OpenAI client works synchronously, so run in executor
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._client.chat.completions.create(
                model=self._model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.7,
            )
        )
