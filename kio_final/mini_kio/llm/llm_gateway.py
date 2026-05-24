from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    success: bool
    content: str
    error: Optional[str] = None


class LLMGateway:
    """
    Gate 3A foundation only.

    No execution authority.
    No tool routing.
    No autonomous behavior.
    """

    async def generate(self, prompt: str) -> LLMResponse:
        raise NotImplementedError("Provider implementation not connected yet.")