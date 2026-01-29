import os
from typing import Optional, Any, AsyncIterator

from btflow.core.logging import logger
from btflow.llm.base import LLMProvider, MessageChunk
from btflow.messages import Message


class AnthropicProvider(LLMProvider):
    """Async Anthropic provider (requires anthropic package)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        try:
            from anthropic import AsyncAnthropic
        except ImportError as e:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install anthropic"
            ) from e

        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            logger.warning("⚠️ ANTHROPIC_API_KEY not found in env!")
        self.client = AsyncAnthropic(api_key=key, base_url=base_url)

    async def generate_text(
        self,
        prompt: Any,
        model: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        timeout: float = 60.0,
        max_tokens: int = 1024,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[object] = None,
        strict_tools: bool = False,
        **kwargs
    ) -> Message:
        # Note: Anthropic system prompt is a dedicated field in messages.create
        response = await self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_instruction or "",
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout,
        )

        content = ""
        if response.content:
            first = response.content[0]
            if hasattr(first, "text"):
                content = first.text or ""

        # tool_calls handling for Anthropic would go here if needed.
        return Message(
            role="assistant",
            content=content,
            metadata={"raw": response}
        )

    async def generate_stream(
        self,
        prompt: Any,
        model: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        timeout: float = 60.0,
        max_tokens: int = 1024,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[object] = None,
        strict_tools: bool = False,
        **kwargs
    ) -> AsyncIterator[MessageChunk]:
        async with self.client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_instruction or "",
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    yield MessageChunk(text=event.delta.text, raw=event)
                elif event.type == "message_start":
                    yield MessageChunk(metadata={"message": event.message}, raw=event)
