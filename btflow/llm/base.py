from abc import ABC, abstractmethod
from dataclasses import dataclass
import os
from typing import Any, Optional, List, Dict, AsyncIterator
from btflow.messages import Message


@dataclass
class MessageChunk:
    text: str = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    raw: Optional[Any] = None


class LLMProvider(ABC):
    @abstractmethod
    async def generate_text(
        self,
        prompt: Any,
        model: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        timeout: float = 60.0,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        strict_tools: bool = False,
        **kwargs
    ) -> Message:
        raise NotImplementedError

    async def generate_stream(
        self,
        prompt: Any,
        model: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        timeout: float = 60.0,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        strict_tools: bool = False,
        **kwargs
    ) -> AsyncIterator[MessageChunk]:
        raise NotImplementedError

    @classmethod
    def default(
        cls,
        preference: Optional[List[str]] = None,
        **kwargs,
    ) -> "LLMProvider":
        """Create a default LLMProvider based on available env keys."""
        order = preference or ["openai", "gemini", "anthropic"]
        api_key = kwargs.get("api_key")

        for name in order:
            if name == "openai":
                if api_key or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY"):
                    from btflow.llm.providers.openai import OpenAIProvider
                    return OpenAIProvider(**kwargs)
            elif name == "gemini":
                if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
                    from btflow.llm.providers.gemini import GeminiProvider
                    return GeminiProvider(**kwargs)
            elif name == "anthropic":
                if os.getenv("ANTHROPIC_API_KEY"):
                    from btflow.llm.providers.anthropic import AnthropicProvider
                    return AnthropicProvider(**kwargs)

        raise RuntimeError(
            "No LLM provider configured. Set one of: OPENAI_API_KEY (or API_KEY), "
            "GOOGLE_API_KEY/GEMINI_API_KEY, or ANTHROPIC_API_KEY."
        )

