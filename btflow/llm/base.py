from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LLMResponse:
    text: str
    raw: Optional[Any] = None


class LLMProvider(ABC):
    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        model: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        timeout: float = 60.0,
    ) -> LLMResponse:
        raise NotImplementedError
