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
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[object] = None,
        strict_tools: bool = False,
    ) -> LLMResponse:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        tool_payload = None
        if tools:
            tool_payload = [
                {"type": "function", "function": t} if "type" not in t else t
                for t in tools
            ]
            if tool_choice is None:
                tool_choice = "required" if strict_tools else "auto"

        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            timeout=timeout,
            tools=tool_payload,
            tool_choice=tool_choice,
        )

        message = response.choices[0].message
        content = message.content or ""
        tool_calls = []
        if getattr(message, "tool_calls", None):
            for tc in message.tool_calls:
                fn = getattr(tc, "function", None)
                if fn is not None:
                    tool_calls.append({"name": fn.name, "arguments": fn.arguments})
        if getattr(message, "function_call", None):
            fn = message.function_call
            tool_calls.append({"name": fn.name, "arguments": fn.arguments})
        return LLMResponse(text=content, raw=response, tool_calls=tool_calls or None)
