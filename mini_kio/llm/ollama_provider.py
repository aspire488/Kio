import logging
import asyncio
import json
import time
from typing import Optional
import httpx
from mini_kio.llm.provider_base import LLMProvider
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """
    Local LLM provider via Ollama (OpenAI-compatible API).

    Runs fully offline — no API key, no network egress.
    Falls back to deterministic formatting when Ollama is unreachable.
    Priority 8 in the provider chain (lowest — final attempt before fallback).

    Creates a fresh httpx client per request to avoid cross-event-loop
    restrictions in Python 3.14+.
    """

    def __init__(self, base_url: str = "http://localhost:11434",
                 model: str = "qwen3:8b", timeout_s: float = 30.0,
                 max_tokens: int = 512):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._default_timeout_s = timeout_s
        self._default_max_tokens = max_tokens
        logger.info(
            f"Ollama provider: endpoint={self._base_url}/api/chat, "
            f"model={self._model}"
        )

    @property
    def provider_name(self) -> str:
        return "ollama"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        safe_timeout = min(request.timeout_s, self._default_timeout_s)
        safe_max_tokens = min(request.max_tokens, self._default_max_tokens)
        start_time = time.monotonic()

        logger.debug(f"Ollama generate: starting, prompt_len={len(request.prompt)}")

        try:
            response = await asyncio.wait_for(
                self._call_api(request.prompt, safe_max_tokens),
                timeout=safe_timeout,
            )
        except asyncio.TimeoutError:
            latency = (time.monotonic() - start_time) * 1000
            logger.warning(f"Ollama generate: timeout after {latency:.0f}ms")
            return LLMResponse(
                success=False,
                status=LLMStatus.TIMEOUT,
                content="",
                error_code="OLLAMA_TIMEOUT",
                latency_ms=latency,
                provider=self.provider_name,
            )
        except (httpx.ConnectError, httpx.RemoteProtocolError, ConnectionRefusedError):
            latency = (time.monotonic() - start_time) * 1000
            logger.warning(f"Ollama generate: connection refused ({latency:.0f}ms)")
            return LLMResponse(
                success=False,
                status=LLMStatus.ERROR,
                content="",
                error_code="OLLAMA_UNREACHABLE",
                latency_ms=latency,
                provider=self.provider_name,
            )
        except Exception as e:
            latency = (time.monotonic() - start_time) * 1000
            logger.warning(f"Ollama generate: exception {type(e).__name__} ({latency:.0f}ms)")
            return LLMResponse(
                success=False,
                status=LLMStatus.ERROR,
                content="",
                error_code=f"OLLAMA_ERROR: {type(e).__name__}",
                latency_ms=latency,
                provider=self.provider_name,
            )

        latency = (time.monotonic() - start_time) * 1000

        if response is None:
            logger.warning(f"Ollama generate: empty response ({latency:.0f}ms)")
            return LLMResponse(
                success=False,
                status=LLMStatus.MALFORMED,
                content="",
                error_code="OLLAMA_EMPTY_RESPONSE",
                latency_ms=latency,
                provider=self.provider_name,
            )

        logger.debug(f"Ollama generate: success, content_len={len(response)}, latency={latency:.0f}ms")
        return LLMResponse(
            success=True,
            status=LLMStatus.SUCCESS,
            content=response,
            latency_ms=latency,
            provider=self.provider_name,
        )

    async def _call_api(self, prompt: str, max_tokens: int) -> Optional[str]:
        client = httpx.AsyncClient(timeout=self._default_timeout_s)
        try:
            payload = {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "options": {
                    "num_predict": max_tokens,
                },
                "stream": False,
            }

            http_response = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )

            if http_response.status_code != 200:
                logger.warning(
                    f"Ollama API: HTTP {http_response.status_code} "
                    f"({http_response.text[:200]})"
                )
                return None

            try:
                data = http_response.json()
            except (json.JSONDecodeError, ValueError):
                logger.warning("Ollama API: malformed JSON response")
                return None

            msg = data.get("message", {})
            content = (msg.get("content") or msg.get("thinking") or "").strip()
            if not content:
                logger.warning("Ollama API: empty content in response")
                return None

            return content
        finally:
            await client.aclose()

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
        pass
