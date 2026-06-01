import logging
import asyncio
import json
import time
from typing import Optional
import httpx
from mini_kio.llm.provider_base import LLMProvider
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus

logger = logging.getLogger(__name__)


class FreeLLMProvider(LLMProvider):
    """
    Lightweight HTTP-based conversational provider for FreeLLMAPI.
    Text-in / text-out only. No SDKs, no tools, no streaming.
    Routes to a local OpenAI-compatible chat completions endpoint.
    """

    def __init__(self, base_url: str, api_key: str = "",
                 model: str = "auto", timeout_s: float = 15.0,
                 max_tokens: int = 200):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._default_timeout_s = timeout_s
        self._default_max_tokens = max_tokens
        self._client = httpx.AsyncClient(timeout=timeout_s)
        logger.info(
            f"FreeLLM provider: endpoint={self._base_url}, "
            f"model={self._model}"
        )

    @property
    def provider_name(self) -> str:
        return "freellm"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        safe_timeout = min(request.timeout_s, self._default_timeout_s)
        safe_max_tokens = min(request.max_tokens, self._default_max_tokens)
        start_time = time.monotonic()

        logger.debug(f"FreeLLM generate: starting, prompt_len={len(request.prompt)}")

        try:
            response = await asyncio.wait_for(
                self._call_api(request.prompt, safe_max_tokens),
                timeout=safe_timeout,
            )
        except asyncio.TimeoutError:
            latency = (time.monotonic() - start_time) * 1000
            logger.warning(f"FreeLLM generate: timeout after {latency:.0f}ms")
            return LLMResponse(
                success=False,
                status=LLMStatus.TIMEOUT,
                content="",
                error_code="FREELLM_TIMEOUT",
                latency_ms=latency,
                provider=self.provider_name,
            )
        except (httpx.ConnectError, httpx.RemoteProtocolError, ConnectionRefusedError):
            latency = (time.monotonic() - start_time) * 1000
            logger.warning(f"FreeLLM generate: connection refused ({latency:.0f}ms)")
            return LLMResponse(
                success=False,
                status=LLMStatus.ERROR,
                content="",
                error_code="FREELLM_UNREACHABLE",
                latency_ms=latency,
                provider=self.provider_name,
            )
        except Exception as e:
            latency = (time.monotonic() - start_time) * 1000
            logger.warning(f"FreeLLM generate: exception {type(e).__name__} ({latency:.0f}ms)")
            return LLMResponse(
                success=False,
                status=LLMStatus.ERROR,
                content="",
                error_code=f"FREELLM_ERROR: {type(e).__name__}",
                latency_ms=latency,
                provider=self.provider_name,
            )

        latency = (time.monotonic() - start_time) * 1000

        if response is None:
            logger.warning(f"FreeLLM generate: empty response ({latency:.0f}ms)")
            return LLMResponse(
                success=False,
                status=LLMStatus.MALFORMED,
                content="",
                error_code="FREELLM_EMPTY_RESPONSE",
                latency_ms=latency,
                provider=self.provider_name,
            )

        logger.debug(f"FreeLLM generate: success, content_len={len(response)}, latency={latency:.0f}ms")
        return LLMResponse(
            success=True,
            status=LLMStatus.SUCCESS,
            content=response,
            latency_ms=latency,
            provider=self.provider_name,
        )

    async def _call_api(self, prompt: str, max_tokens: int) -> Optional[str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }

        try:
            http_response = await self._client.post(
                self._base_url,
                headers=headers,
                json=payload,
            )
        except Exception:
            raise

        if http_response.status_code != 200:
            logger.warning(
                f"FreeLLM API: HTTP {http_response.status_code} "
                f"({http_response.text[:100]})"
            )
            return None

        try:
            data = http_response.json()
        except (json.JSONDecodeError, ValueError):
            logger.warning("FreeLLM API: malformed JSON response")
            return None

        if "choices" not in data or not data["choices"]:
            logger.warning("FreeLLM API: response missing choices")
            return None

        try:
            content = data["choices"][0].get("message", {}).get("content", "")
        except (IndexError, KeyError, TypeError, AttributeError):
            logger.warning("FreeLLM API: malformed message in choices")
            return None

        if not content:
            logger.warning("FreeLLM API: empty content in response")
            return None

        return content.strip()

    async def health_check(self) -> bool:
        try:
            await asyncio.wait_for(
                self._call_api("ping", 5),
                timeout=5.0,
            )
            return True
        except Exception:
            return False

    async def close(self):
        await self._client.aclose()
