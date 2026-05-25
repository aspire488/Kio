import logging
import asyncio
from typing import Optional
from mini_kio.llm.provider_base import LLMProvider
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
except ImportError:
    genai = None


class GeminiProvider(LLMProvider):
    """
    Bounded Gemini conversational provider.
    Text-in / text-out only. No tools, no streaming, no autonomous behavior.
    Model name is configurable via GEMINI_MODEL (default: gemini-2.0-flash).
    """

    def __init__(self, api_key: str, timeout_s: float = 15.0, max_tokens: int = 200,
                 model_name: str = "gemini-2.0-flash"):
        self._api_key = api_key
        self._default_timeout_s = timeout_s
        self._default_max_tokens = max_tokens
        self._model_name = model_name
        self._model = None
        if genai and api_key:
            try:
                genai.configure(api_key=api_key)
                self._model = genai.GenerativeModel(self._model_name)
            except Exception:
                self._model = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if self._model is None:
            return LLMResponse(
                success=False,
                status=LLMStatus.ERROR,
                content="",
                error_code="GEMINI_NOT_CONFIGURED",
                provider=self.provider_name,
            )

        safe_timeout = min(request.timeout_s, self._default_timeout_s)
        safe_max_tokens = min(request.max_tokens, self._default_max_tokens)

        try:
            response = await asyncio.wait_for(
                self._call_gemini(request.prompt, safe_max_tokens),
                timeout=safe_timeout,
            )
            return LLMResponse(
                success=True,
                status=LLMStatus.SUCCESS,
                content=response,
                provider=self.provider_name,
            )
        except asyncio.TimeoutError:
            return LLMResponse(
                success=False,
                status=LLMStatus.TIMEOUT,
                content="",
                error_code="GEMINI_TIMEOUT",
                provider=self.provider_name,
            )
        except Exception as e:
            error_str = str(e)[:120]
            if "quota" in error_str.lower() or "rate" in error_str.lower() or "429" in error_str:
                return LLMResponse(
                    success=False,
                    status=LLMStatus.DEGRADED,
                    content="",
                    error_code="GEMINI_QUOTA_EXCEEDED",
                    provider=self.provider_name,
                )
            if "api_key" in error_str.lower() or "api key" in error_str.lower() or "unauthorized" in error_str.lower():
                return LLMResponse(
                    success=False,
                    status=LLMStatus.ERROR,
                    content="",
                    error_code="GEMINI_AUTH_ERROR",
                    provider=self.provider_name,
                )
            return LLMResponse(
                success=False,
                status=LLMStatus.ERROR,
                content="",
                error_code=f"GEMINI_ERROR: {error_str[:60]}",
                provider=self.provider_name,
            )

    async def health_check(self) -> bool:
        return self._model is not None

    async def _call_gemini(self, prompt: str, max_tokens: int) -> str:
        loop = asyncio.get_event_loop()

        def _sync_call() -> str:
            result = self._model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.7,
                    top_p=0.9,
                ),
                safety_settings={
                    genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                },
            )
            return result.text if result else ""

        return await loop.run_in_executor(None, _sync_call)
