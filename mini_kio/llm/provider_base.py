from abc import ABC, abstractmethod
from typing import Dict, Any
from mini_kio.llm.models import LLMRequest, LLMResponse


class LLMProvider(ABC):
    """
    Abstract base provider for LLM integrations.
    Bounded to text-in/text-out only.
    No access to runtime or tools.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Pure generation method.
        Must respect timeout and max_tokens from request.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check provider availability without full generation.
        """
        pass
