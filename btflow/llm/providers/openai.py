import os
from typing import Optional

from btflow.core.logging import logger
from btflow.llm.base import LLMResponse, LLMProvider


class OpenAIProvider(LLMProvider):
    """Async OpenAI chat provider (requires openai package)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
    ):
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai package not installed. Run: pip install openai"
            ) from e

        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            logger.warning("⚠️ OPENAI_API_KEY not found in env!")
        self.client = AsyncOpenAI(api_key=key, base_url=base_url, organization=organization)

    async def generate_text(
        self,
        prompt: str,
        model: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        timeout: float = 60.0,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            timeout=timeout,
        )

        content = response.choices[0].message.content or ""
        return LLMResponse(text=content, raw=response)
