import asyncio
import os
from typing import Optional, Any, AsyncIterator

from google import genai
from google.genai import types

from btflow.core.logging import logger
from btflow.llm.base import LLMProvider, MessageChunk
from btflow.messages import Message


class GeminiProvider(LLMProvider):
    """Thin wrapper around google-genai for async content generation."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
        self.base_url = base_url or os.getenv("BASE_URL")
        
        if not self.api_key:
            logger.warning("⚠️ Gemini API key not found in env (GOOGLE_API_KEY/GEMINI_API_KEY)")
            
        http_options = None
        if self.base_url:
            logger.debug(f"🔌 [GeminiProvider] Using custom Base URL: {self.base_url}")
            http_options = {"base_url": self.base_url}
            
        self.client = genai.Client(api_key=self.api_key, http_options=http_options)

    async def generate_text(
        self,
        prompt: Any,
        model: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = 40,
        timeout: float = 60.0,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[object] = None,
        strict_tools: bool = False,
        **kwargs
    ) -> Message:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )
        response = await asyncio.wait_for(
            self.client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            ),
            timeout=timeout,
        )
        # Note: tool_calls handling for Gemini would go here if structured calls are used.
        # For now, we return the text content wrapped in a Message.
        return Message(
            role="assistant",
            content=response.text or "",
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
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[object] = None,
        strict_tools: bool = False,
        **kwargs
    ):
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )
        # Note: generate_content_stream returns an async generator directly, no await needed
        stream = self.client.aio.models.generate_content_stream(
            model=model,
            contents=prompt,
            config=config,
        )
        async for chunk in stream:
            text = getattr(chunk, "text", "") or ""
            
            tool_calls = None
            # Extract tool calls from Gemini chunk if present
            if hasattr(chunk, "candidates") and chunk.candidates:
                first = chunk.candidates[0]
                if hasattr(first, "content") and hasattr(first.content, "parts"):
                    for part in first.content.parts:
                        if hasattr(part, "call"):
                            tc = part.call
                            if tool_calls is None:
                                tool_calls = []
                            tool_calls.append({"name": tc.name, "arguments": tc.args})

            if not text and not tool_calls:
                continue
            yield MessageChunk(text=text, tool_calls=tool_calls, raw=chunk)
