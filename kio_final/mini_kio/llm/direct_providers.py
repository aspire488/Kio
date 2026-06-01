"""
direct_providers.py — Lightweight HTTP providers for Together AI, Cerebras, OpenRouter

Text-in/text-out only. No SDKs, no tools, no streaming, no actions.
Each provider is a stateless HTTP client with per-provider error classification.
"""

import asyncio
import json
import logging
import time
from typing import Optional
import httpx
from mini_kio.llm.provider_base import LLMProvider
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus

logger = logging.getLogger(__name__)


class DirectHTTPProvider(LLMProvider):
    """
    Generic OpenAI-compatible HTTP provider for direct API calls.

    Used for Together AI, Cerebras, OpenRouter — all expose
    /v1/chat/completions endpoints with the same payload format.
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str = "",
        timeout_s: float = 10.0,
        max_tokens: int = 200,
    ):
        self._name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._default_timeout_s = timeout_s
        self._default_max_tokens = max_tokens
        logger.info(
            f"DirectHTTP provider '{name}': endpoint={base_url}, "
            f"model={model or 'default'}"
        )

    @property
    def provider_name(self) -> str:
        return self._name

    async def generate(self, request: LLMRequest) -> LLMResponse:
        safe_timeout = min(request.timeout_s, self._default_timeout_s)
        safe_max_tokens = min(request.max_tokens, self._default_max_tokens)
        start_time = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=safe_timeout) as client:
                response = await asyncio.wait_for(
                    self._call_api(request.prompt, safe_max_tokens, client),
                    timeout=safe_timeout,
                )
        except asyncio.TimeoutError:
            latency = (time.monotonic() - start_time) * 1000
            logger.warning(f"{self._name} generate: timeout ({latency:.0f}ms)")
            return LLMResponse(
                success=False, status=LLMStatus.TIMEOUT, content="",
                error_code=f"{self._name.upper()}_TIMEOUT",
                latency_ms=latency, provider=self._name,
            )
        except (httpx.ConnectError, httpx.RemoteProtocolError):
            latency = (time.monotonic() - start_time) * 1000
            logger.warning(f"{self._name} generate: connection refused ({latency:.0f}ms)")
            return LLMResponse(
                success=False, status=LLMStatus.ERROR, content="",
                error_code=f"{self._name.upper()}_UNREACHABLE",
                latency_ms=latency, provider=self._name,
            )
        except httpx.HTTPStatusError as e:
            latency = (time.monotonic() - start_time) * 1000
            code = self._classify_http_error(e.response.status_code, str(e))
            logger.warning(f"{self._name} generate: HTTP {e.response.status_code} ({latency:.0f}ms)")
            return LLMResponse(
                success=False, status=LLMStatus.ERROR, content="",
                error_code=code, latency_ms=latency, provider=self._name,
            )
        except RuntimeError:
            latency = (time.monotonic() - start_time) * 1000
            logger.warning(f"{self._name} generate: RuntimeError - likely event loop mismatch ({latency:.0f}ms)")
            return LLMResponse(
                success=False, status=LLMStatus.ERROR, content="",
                error_code=f"{self._name.upper()}_RUNTIME_ERROR",
                latency_ms=latency, provider=self._name,
            )
        except Exception as e:
            latency = (time.monotonic() - start_time) * 1000
            logger.warning(f"{self._name} generate: {type(e).__name__} ({latency:.0f}ms)")
            return LLMResponse(
                success=False, status=LLMStatus.ERROR, content="",
                error_code=f"{self._name.upper()}_ERROR: {type(e).__name__}",
                latency_ms=latency, provider=self._name,
            )

        latency = (time.monotonic() - start_time) * 1000

        if response is None:
            return LLMResponse(
                success=False, status=LLMStatus.MALFORMED, content="",
                error_code=f"{self._name.upper()}_EMPTY_RESPONSE",
                latency_ms=latency, provider=self._name,
            )

        return LLMResponse(
            success=True, status=LLMStatus.SUCCESS,
            content=response, latency_ms=latency,
            provider=self._name,
        )

    async def _call_api(self, prompt: str, max_tokens: int, client: httpx.AsyncClient) -> Optional[str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }

        http_response = await client.post(
            self._base_url.rstrip("/") + "/v1/chat/completions",
            headers=headers, json=payload,
        )
        http_response.raise_for_status()

        try:
            data = http_response.json()
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"{self._name} API: malformed JSON")
            return None

        if "choices" not in data or not data["choices"]:
            logger.warning(f"{self._name} API: missing choices")
            return None

        try:
            content = data["choices"][0].get("message", {}).get("content", "")
        except (IndexError, KeyError, TypeError, AttributeError):
            logger.warning(f"{self._name} API: malformed message")
            return None

        if not content:
            logger.warning(f"{self._name} API: empty content")
            return None

        return content.strip()

    def _classify_http_error(self, status_code: int, body: str) -> str:
        prefix = self._name.upper()
        if status_code == 429:
            return f"{prefix}_RATE_LIMITED"
        if status_code == 401 or status_code == 403:
            return f"{prefix}_AUTH_ERROR"
        if status_code == 503 or status_code == 502:
            return f"{prefix}_UNAVAILABLE"
        if status_code >= 500:
            return f"{prefix}_SERVER_ERROR"
        return f"{prefix}_HTTP_{status_code}"

    async def health_check(self) -> bool:
        return bool(self._api_key)
