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
    Model name is configurable via GEMINI_MODEL (default: gemini-2.5-flash).
    Falls back to GEMINI_FALLBACK_MODEL (default: gemini-2.0-flash) on empty response.
    """

    def __init__(self, api_key: str, timeout_s: float = 15.0, max_tokens: int = 200,
                 model_name: str = "gemini-2.5-flash",
                 fallback_model_name: str = "gemini-2.0-flash"):
        self._api_key = api_key
        self._default_timeout_s = timeout_s
        self._default_max_tokens = max_tokens
        self._model_name = model_name
        self._fallback_model_name = fallback_model_name
        self._model = None
        self._fallback_model = None
        if genai and api_key:
            try:
                genai.configure(api_key=api_key)
                self._model = genai.GenerativeModel(self._model_name)
                logger.info(f"Gemini provider: active model = {self._model_name}")
                if self._fallback_model_name:
                    try:
                        self._fallback_model = genai.GenerativeModel(self._fallback_model_name)
                        logger.info(f"Gemini provider: fallback model = {self._fallback_model_name}")
                    except Exception:
                        logger.warning(f"Gemini provider: fallback model {self._fallback_model_name} unavailable")
                        self._fallback_model = None
            except Exception:
                self._model = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if self._model is None:
            logger.warning("Gemini provider generate: model is None (not configured)")
            return LLMResponse(
                success=False,
                status=LLMStatus.ERROR,
                content="",
                error_code="GEMINI_NOT_CONFIGURED",
                provider=self.provider_name,
            )

        safe_timeout = min(request.timeout_s, self._default_timeout_s)
        safe_max_tokens = min(request.max_tokens, self._default_max_tokens)

        models_to_try = [(self._model, self._model_name)]
        if self._fallback_model is not None:
            models_to_try.append((self._fallback_model, self._fallback_model_name))

        for model, name in models_to_try:
            try:
                response = await asyncio.wait_for(
                    self._call_gemini(model, request.prompt, safe_max_tokens),
                    timeout=safe_timeout,
                )

                if response:
                    logger.debug(f"Gemini provider generate: success via {name}, content_len={len(response)}")
                    return LLMResponse(
                        success=True,
                        status=LLMStatus.SUCCESS,
                        content=response,
                        provider=self.provider_name,
                    )

                logger.warning(f"Gemini provider generate: empty response from {name}")
                if name != models_to_try[-1][1]:
                    logger.info(f"Gemini provider generate: falling back to next model")

            except asyncio.TimeoutError:
                logger.warning(f"Gemini provider generate: timeout on {name}")
                if name != models_to_try[-1][1]:
                    logger.info(f"Gemini provider generate: timeout, falling back to next model")
                else:
                    return LLMResponse(
                        success=False,
                        status=LLMStatus.TIMEOUT,
                        content="",
                        error_code="GEMINI_TIMEOUT",
                        provider=self.provider_name,
                    )
            except Exception as e:
                error_str = str(e)[:120]
                error_type = type(e).__name__
                if "quota" in error_str.lower() or "rate" in error_str.lower() or "429" in error_str:
                    logger.warning(f"Gemini provider generate: quota exceeded on {name}")
                    return LLMResponse(
                        success=False,
                        status=LLMStatus.DEGRADED,
                        content="",
                        error_code="GEMINI_QUOTA_EXCEEDED",
                        provider=self.provider_name,
                    )
                elif "404" in error_str.lower() or "model removed" in error_str.lower() or "model unsupported" in error_str.lower() or "model unavailable" in error_str.lower():
                    logger.warning(f"Gemini provider generate: model not found/unavailable on {name}")
                    return LLMResponse(
                        success=False,
                        status=LLMStatus.ERROR,
                        content="",
                        error_code="GEMINI_MODEL_NOT_FOUND",
                        provider=self.provider_name,
                    )
                if "api_key" in error_str.lower() or "api key" in error_str.lower() or "unauthorized" in error_str.lower():
                    logger.warning(f"Gemini provider generate: auth error on {name}")
                    return LLMResponse(
                        success=False,
                        status=LLMStatus.ERROR,
                        content="",
                        error_code="GEMINI_AUTH_ERROR",
                        provider=self.provider_name,
                    )

                logger.warning(f"Gemini provider generate: exception on {name}: {error_type} - {error_str[:60]}")
                if name != models_to_try[-1][1]:
                    logger.info(f"Gemini provider generate: falling back after {name} error")
                else:
                    return LLMResponse(
                        success=False,
                        status=LLMStatus.ERROR,
                        content="",
                        error_code=f"GEMINI_ERROR: {error_str[:60]}",
                        provider=self.provider_name,
                    )

        logger.warning("Gemini provider generate: all models exhausted, returning empty")
        return LLMResponse(
            success=False,
            status=LLMStatus.MALFORMED,
            content="",
            error_code="GEMINI_EMPTY_RESPONSE",
            provider=self.provider_name,
        )

    async def health_check(self) -> bool:
        return self._model is not None

    def _extract_text(self, result) -> str:
        """Extract text from a Gemini GenerateContentResponse with per-path diagnostics."""
        if not result:
            logger.warning("Gemini extract: result object is falsy")
            return ""

        # Path 1 — result.text (primary)
        try:
            text = result.text
            if text:
                logger.debug(f"Gemini extract: path=text, len={len(text)}")
                return text
            logger.debug("Gemini extract: result.text is empty string")
        except ValueError:
            logger.warning("Gemini extract: result.text raised ValueError (likely safety-blocked)")
        except AttributeError:
            logger.warning("Gemini extract: result.text attribute missing on response")
        except Exception as e:
            logger.warning(f"Gemini extract: result.text unexpected error: {type(e).__name__}")

        # Path 2 — candidates fallback
        try:
            candidates = getattr(result, "candidates", None)
            if candidates is None:
                logger.debug("Gemini extract: no candidates attribute")
            elif len(candidates) == 0:
                logger.debug("Gemini extract: candidates list is empty")
            else:
                candidate = candidates[0]
                content = getattr(candidate, "content", None)
                if content is None:
                    logger.debug("Gemini extract: candidate has no content")
                else:
                    parts = getattr(content, "parts", None)
                    if parts is None:
                        logger.debug("Gemini extract: content has no parts")
                    elif len(parts) == 0:
                        logger.debug("Gemini extract: parts list is empty")
                    else:
                        text = getattr(parts[0], "text", None)
                        if text:
                            logger.debug(f"Gemini extract: path=candidates, len={len(text)}")
                            return text
                        logger.debug("Gemini extract: first part text is empty")
        except Exception as e:
            logger.warning(f"Gemini extract: candidates path error: {type(e).__name__}")

        # Path 3 — blocked response diagnostics
        try:
            feedback = getattr(result, "prompt_feedback", None)
            if feedback is not None:
                block_reason = getattr(feedback, "block_reason", None)
                logger.warning(f"Gemini extract: prompt blocked, reason={block_reason}")
            else:
                logger.debug("Gemini extract: no prompt_feedback available")
        except Exception as e:
            logger.debug(f"Gemini extract: feedback diagnostic error: {type(e).__name__}")

        logger.warning("Gemini extract: all extraction paths exhausted, returning empty")
        return ""

    async def _call_gemini(self, model, prompt: str, max_tokens: int) -> str:
        loop = asyncio.get_event_loop()

        def _sync_call() -> str:
            result = model.generate_content(
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
            return self._extract_text(result)

        return await loop.run_in_executor(None, _sync_call)
