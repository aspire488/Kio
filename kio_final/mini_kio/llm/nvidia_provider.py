import logging
import asyncio
from typing import Optional, Dict

from mini_kio.llm.provider_base import LLMProvider
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


_TASK_MODEL_MAP: Dict[str, str] = {
    "chat": "primary",
    "reasoning": "primary",
    "planning": "primary",
    "coding": "code",
    "debugging": "code",
    "vision": "vision",
}


class NvidiaProvider(LLMProvider):
    """
    NVIDIA NIM provider via OpenAI-compatible endpoint.

    Supports per-task model routing:
      - chat / reasoning / planning  → primary model (Llama 4 Maverick)
      - coding / debugging           → code model (GPT-OSS 120B)
      - vision                       → vision model (Qwen 3.5 397B)
      - fallback                     → fallback model (Llama 3.1 8B)

    Follows the same pattern as HuggingFaceProvider: uses openai.OpenAI
    client configured with NVIDIA_BASE_URL and NVIDIA_API_KEY.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        primary_model: str,
        code_model: str,
        vision_model: str,
        fallback_model: str,
        timeout_s: float = 15.0,
        max_tokens: int = 1024,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._primary_model = primary_model
        self._code_model = code_model
        self._vision_model = vision_model
        self._fallback_model = fallback_model
        self._default_timeout_s = timeout_s
        self._default_max_tokens = max_tokens
        self._client = None

        if OpenAI and api_key:
            try:
                self._client = OpenAI(
                    base_url=self._base_url,
                    api_key=api_key,
                    timeout=timeout_s,
                )
                logger.info(
                    "NvidiaProvider: client initialized, endpoint=%s, "
                    "primary=%s, code=%s, vision=%s, fallback=%s",
                    self._base_url, primary_model, code_model,
                    vision_model, fallback_model,
                )
            except Exception as e:
                logger.error("NvidiaProvider: Failed to initialize OpenAI client: %s", e)
                self._client = None

    @property
    def provider_name(self) -> str:
        return "nvidia"

    # ── Model routing ─────────────────────────────────────────────────

    def resolve_model(self, task_type: str) -> str:
        """Return the model name for a given task type (public API)."""
        bucket = _TASK_MODEL_MAP.get(task_type, "primary")
        if bucket == "code":
            return self._code_model
        if bucket == "vision":
            return self._vision_model
        return self._primary_model

    def resolve_cognition_model(self, intent: str) -> str:
        """Return the model name for a given cognitive intent (Phase 3).

        Maps intent strings to model names per the cognition routing table:
          chat/qa/reasoning/planning → primary (Maverick)
          architecture/coding/debugging/agent → code (GPT-OSS)
          vision/ocr/screen_analysis → vision (Qwen)
          fallback → fallback model
        """
        code_intents = frozenset({"architecture", "coding", "debugging", "agent"})
        vision_intents = frozenset({"vision", "ocr", "screen_analysis"})
        if intent in code_intents:
            return self._code_model
        if intent in vision_intents:
            return self._vision_model
        return self._primary_model

    def _select_model(self, task_type: str) -> str:
        bucket = _TASK_MODEL_MAP.get(task_type, "primary")
        if bucket == "code":
            return self._code_model
        if bucket == "vision":
            return self._vision_model
        return self._primary_model

    # ── Generate ───────────────────────────────────────────────────────

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if self._client is None:
            logger.warning("NvidiaProvider generate: client is None (not configured)")
            return LLMResponse(
                success=False, status=LLMStatus.ERROR, content="",
                error_code="NVIDIA_NOT_CONFIGURED", provider=self.provider_name,
            )

        safe_timeout = min(request.timeout_s, self._default_timeout_s)
        safe_max_tokens = min(request.max_tokens, self._default_max_tokens)

        task_type = request.metadata.get("task_type", "chat")
        model = self._select_model(task_type)
        logger.info("[NVIDIA_ROUTE] task_type=%s model=%s", task_type, model)

        content = await self._attempt(model, request.prompt, safe_max_tokens, safe_timeout)
        if content is not None:
            return LLMResponse(
                success=True, status=LLMStatus.SUCCESS,
                content=content, provider=self.provider_name,
            )

        logger.info("NvidiaProvider: primary model '%s' failed, trying fallback '%s'", model, self._fallback_model)
        content = await self._attempt(self._fallback_model, request.prompt, safe_max_tokens, safe_timeout)
        if content is not None:
            return LLMResponse(
                success=True, status=LLMStatus.SUCCESS,
                content=content, provider=self.provider_name,
            )

        return LLMResponse(
            success=False, status=LLMStatus.ERROR, content="",
            error_code="NVIDIA_ALL_MODELS_FAILED", provider=self.provider_name,
        )

    async def _attempt(self, model: str, prompt: str, max_tokens: int, timeout_s: float) -> Optional[str]:
        try:
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self._client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                        temperature=0.7,
                    ),
                ),
                timeout=timeout_s,
            )
            if response and response.choices and response.choices[0].message.content:
                return response.choices[0].message.content.strip()
            return None
        except asyncio.TimeoutError:
            logger.warning("NvidiaProvider: model '%s' timeout", model)
            return None
        except Exception as e:
            error_str = str(e)[:120]
            logger.debug("NvidiaProvider: model '%s' failed: %s", model, error_str[:60])
            return None

    # ── Health check ───────────────────────────────────────────────────

    async def health_check(self) -> bool:
        if self._client is None:
            return False
        try:
            loop = asyncio.get_event_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self._client.models.list()),
                timeout=5.0,
            )
            return True
        except Exception:
            return bool(self._api_key)
